using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace ChatArchive;

public sealed class ImageViewerWindow : Window
{
    readonly BitmapSource bitmap;
    readonly ScrollViewer viewport;
    readonly Canvas canvas;
    readonly ScaleTransform scale=new(1,1);
    readonly TextBlock percentage;
    readonly Button smaller;
    readonly Button larger;
    double zoom=1;
    bool fitting=true;
    bool fitPending;
    bool closed;
    Point? dragStart;
    Vector dragOffsets;

    public ImageViewerWindow(BitmapSource source)
    {
        bitmap=source;
        Title=$"图片 · {bitmap.PixelWidth} × {bitmap.PixelHeight} 像素";
        Width=Math.Min(1100,SystemParameters.WorkArea.Width);Height=Math.Min(850,SystemParameters.WorkArea.Height);
        MinWidth=520;MinHeight=360;WindowStartupLocation=WindowStartupLocation.CenterOwner;
        FontFamily=new FontFamily("Microsoft YaHei UI");FontSize=14;Background=Brushes.White;
        var root=new Grid{Background=Brushes.White};Content=root;
        root.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});
        root.RowDefinitions.Add(new RowDefinition());
        root.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});
        var toolbar=new WrapPanel{Margin=new Thickness(12,8,12,8),VerticalAlignment=VerticalAlignment.Center};
        root.Children.Add(new Border{Child=toolbar,BorderBrush=new SolidColorBrush(Color.FromRgb(225,231,227)),BorderThickness=new Thickness(0,0,0,1)});

        var zoomOut=new RoutedUICommand("缩小","ZoomOut",typeof(ImageViewerWindow));
        var zoomIn=new RoutedUICommand("放大","ZoomIn",typeof(ImageViewerWindow));
        var fit=new RoutedUICommand("适应窗口","Fit",typeof(ImageViewerWindow));
        var actual=new RoutedUICommand("原始尺寸","Actual",typeof(ImageViewerWindow));
        var close=new RoutedUICommand("关闭图片","CloseImage",typeof(ImageViewerWindow));
        Bind(zoomOut,()=>ZoomBy(1/1.25),new KeyGesture(Key.Subtract),new KeyGesture(Key.OemMinus,ModifierKeys.Control));
        Bind(zoomIn,()=>ZoomBy(1.25),new KeyGesture(Key.Add),new KeyGesture(Key.OemPlus,ModifierKeys.Control));
        Bind(fit,FitToWindow,new KeyGesture(Key.D0,ModifierKeys.Control));
        Bind(actual,()=>SetZoom(1),new KeyGesture(Key.D1,ModifierKeys.Control));
        Bind(close,Close,new KeyGesture(Key.Escape));
        smaller=ToolButton("ZoomOut","−","缩小（Ctrl＋减号）",zoomOut);smaller.MinWidth=44;
        larger=ToolButton("ZoomIn","＋","放大（Ctrl＋加号）",zoomIn);larger.MinWidth=44;
        percentage=new TextBlock{Name="ZoomPercentage",MinWidth=72,TextAlignment=TextAlignment.Center,VerticalAlignment=VerticalAlignment.Center,Margin=new Thickness(4)};
        AutomationProperties.SetName(percentage,"当前缩放比例");
        toolbar.Children.Add(smaller);toolbar.Children.Add(percentage);toolbar.Children.Add(larger);
        toolbar.Children.Add(ToolButton("FitImage","适应窗口","适应窗口（Ctrl＋0）",fit));
        toolbar.Children.Add(ToolButton("ActualSize","100%","原始尺寸（Ctrl＋1）",actual));

        var image=new Image{Source=bitmap,Width=bitmap.PixelWidth,Height=bitmap.PixelHeight,Stretch=Stretch.Fill,RenderTransform=scale};
        AutomationProperties.SetName(image,"图片，可使用缩放按钮、滚轮及滚动条查看细节");
        RenderOptions.SetBitmapScalingMode(image,BitmapScalingMode.HighQuality);
        canvas=new Canvas{Name="ImageCanvas",Width=bitmap.PixelWidth,Height=bitmap.PixelHeight,Background=Brushes.Transparent};
        canvas.Children.Add(image);
        viewport=new ScrollViewer{Name="ImageViewport",Content=canvas,HorizontalScrollBarVisibility=ScrollBarVisibility.Auto,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalContentAlignment=HorizontalAlignment.Center,VerticalContentAlignment=VerticalAlignment.Center,Background=new SolidColorBrush(Color.FromRgb(245,247,246)),PanningMode=PanningMode.Both};
        Grid.SetRow(viewport,1);root.Children.Add(viewport);
        var hint=new TextBlock{Text=$"{bitmap.PixelWidth} × {bitmap.PixelHeight} 像素 · 滚轮缩放 · 拖动或滚动条查看细节 · Esc 关闭",TextWrapping=TextWrapping.Wrap,Foreground=new SolidColorBrush(Color.FromRgb(82,102,91)),FontSize=12,Margin=new Thickness(16,10,16,10)};
        Grid.SetRow(hint,2);root.Children.Add(hint);

        viewport.PreviewMouseWheel+=(_,e)=>
        {
            EndDrag();ZoomBy(Math.Pow(1.2,e.Delta/120.0),e.GetPosition(viewport));e.Handled=true;
        };
        canvas.MouseLeftButtonDown+=(_,e)=>
        {
            if(viewport.ScrollableWidth<=0 && viewport.ScrollableHeight<=0) return;
            dragStart=e.GetPosition(viewport);dragOffsets=new Vector(viewport.HorizontalOffset,viewport.VerticalOffset);
            if(canvas.CaptureMouse()) {canvas.Cursor=Cursors.ScrollAll;e.Handled=true;}
            else dragStart=null;
        };
        canvas.MouseMove+=(_,e)=>
        {
            if(dragStart is not Point start) return;
            PanTo(dragOffsets-(e.GetPosition(viewport)-start));e.Handled=true;
        };
        canvas.MouseLeftButtonUp+=(_,e)=>{EndDrag();e.Handled=true;};
        canvas.LostMouseCapture+=(_,_)=>{dragStart=null;UpdateCursor();};
        Loaded+=(_,_)=>{FitToWindow();CommandManager.InvalidateRequerySuggested();};
        viewport.SizeChanged+=(_,_)=>ScheduleFit();
        Closed+=(_,_)=>{closed=true;EndDrag();};
        UpdateControls();
    }

    void Bind(RoutedUICommand command,Action action,params KeyGesture[] gestures)
    {
        CommandBindings.Add(new CommandBinding(command,(_,e)=>{action();e.Handled=true;},(_,e)=>{e.CanExecute=true;e.Handled=true;}));
        foreach(var gesture in gestures) InputBindings.Add(new KeyBinding(command,gesture));
    }

    Button ToolButton(string name,string text,string description,ICommand command)
    {
        var button=new Button{Name=name,Content=text,ToolTip=description,Command=command,CommandTarget=this,MinHeight=40,Padding=new Thickness(14,8,14,8)};
        AutomationProperties.SetName(button,description);return button;
    }

    double FitScale()=>Math.Min(1,Math.Min(Math.Max(1,viewport.ActualWidth-32)/bitmap.PixelWidth,Math.Max(1,viewport.ActualHeight-32)/bitmap.PixelHeight));
    double MinimumZoom=>Math.Min(.01,FitScale());

    void ScheduleFit()
    {
        if(!fitting || !IsLoaded || fitPending || closed) return;
        fitPending=true;
        Dispatcher.BeginInvoke(DispatcherPriority.Loaded,()=>
        {
            fitPending=false;if(fitting && !closed) FitToWindow();
        });
    }

    void FitToWindow()
    {
        EndDrag();fitting=true;ApplyScale(FitScale());
        viewport.ScrollToHorizontalOffset(0);viewport.ScrollToVerticalOffset(0);
    }

    void ZoomBy(double factor,Point? anchor=null)=>SetZoom(zoom*factor,anchor);

    void SetZoom(double value,Point? anchor=null)
    {
        EndDrag();fitting=false;
        var position=anchor ?? new Point(viewport.ViewportWidth/2,viewport.ViewportHeight/2);
        // Account for centering when the image is smaller than the viewport.
        var origin=new Point(Math.Max(0,(viewport.ViewportWidth-canvas.Width)/2),Math.Max(0,(viewport.ViewportHeight-canvas.Height)/2));
        var pixel=new Point((viewport.HorizontalOffset+position.X-origin.X)/zoom,(viewport.VerticalOffset+position.Y-origin.Y)/zoom);
        ApplyScale(Math.Clamp(value,MinimumZoom,8));viewport.UpdateLayout();
        origin=new Point(Math.Max(0,(viewport.ViewportWidth-canvas.Width)/2),Math.Max(0,(viewport.ViewportHeight-canvas.Height)/2));
        PanTo(new Vector(pixel.X*zoom+origin.X-position.X,pixel.Y*zoom+origin.Y-position.Y));
    }

    void ApplyScale(double value)
    {
        zoom=value;scale.ScaleX=value;scale.ScaleY=value;
        canvas.Width=bitmap.PixelWidth*value;canvas.Height=bitmap.PixelHeight*value;
        UpdateControls();
    }

    void PanTo(Vector offsets)
    {
        viewport.ScrollToHorizontalOffset(offsets.X);viewport.ScrollToVerticalOffset(offsets.Y);
    }

    void EndDrag()
    {
        dragStart=null;if(canvas.IsMouseCaptured) canvas.ReleaseMouseCapture();UpdateCursor();
    }

    void UpdateCursor()=>canvas.Cursor=canvas.Width>viewport.ViewportWidth || canvas.Height>viewport.ViewportHeight?Cursors.Hand:Cursors.Arrow;

    void UpdateControls()
    {
        percentage.Text=$"{zoom*100:0.#}%";smaller.IsEnabled=zoom>MinimumZoom+1e-9;larger.IsEnabled=zoom<8-1e-9;
        UpdateCursor();
    }
}
