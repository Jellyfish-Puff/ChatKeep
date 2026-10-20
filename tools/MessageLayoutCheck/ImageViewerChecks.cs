using System.IO;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using ChatArchive;

static class ImageViewerChecks
{
    static int clicks;
    const BindingFlags Flags=BindingFlags.Instance|BindingFlags.NonPublic;
    static T Field<T>(object target,string name)=>(T)target.GetType().GetField(name,Flags)!.GetValue(target)!;
    static void Invoke(object target,string method,params object?[] args)=>target.GetType().GetMethod(method,Flags)!.Invoke(target,args);
    static void Check(bool condition,string name) {if(!condition) throw new InvalidOperationException(name);}
    static async Task Settle(Window window)
    {
        window.UpdateLayout();await window.Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);await Task.Delay(40);window.UpdateLayout();
    }
    static void Click(ImageViewerWindow window,string name)
    {
        var button=Descendants(window).OfType<Button>().Single(b=>b.Name==name);
        clicks++;
        Check(button.IsEnabled,"viewer_button_disabled_"+name+"_click_"+clicks+"_window_"+window.IsEnabled+"_command_"+((RoutedCommand)button.Command).CanExecute(null,window));
        ((RoutedCommand)button.Command).Execute(null,button);
    }
    static IEnumerable<DependencyObject> Descendants(DependencyObject root)
    {
        for(var i=0;i<VisualTreeHelper.GetChildrenCount(root);i++)
        {
            var child=VisualTreeHelper.GetChild(root,i);yield return child;
            foreach(var nested in Descendants(child)) yield return nested;
        }
    }
    static BitmapSource Synthetic(int width,int height)
    {
        var visual=new DrawingVisual();
        using(var drawing=visual.RenderOpen())
        {
            drawing.DrawRectangle(Brushes.White,null,new Rect(0,0,width,height));
            for(var y=0;y<height;y+=160)
            {
                drawing.DrawRectangle(new SolidColorBrush(Color.FromRgb(10,155,125)),null,new Rect(20,y+20,width-40,80));
                drawing.DrawText(new FormattedText("合成图片 · 工作安排 "+(y/160+1),System.Globalization.CultureInfo.CurrentCulture,FlowDirection.LeftToRight,new Typeface("Microsoft YaHei UI"),28,Brushes.White,1),new Point(36,y+38));
            }
        }
        var bitmap=new RenderTargetBitmap(width,height,96,96,PixelFormats.Pbgra32);bitmap.Render(visual);bitmap.Freeze();return bitmap;
    }
    static void Screenshot(Window window,string folder,string name)
    {
        Directory.CreateDirectory(folder);var content=(FrameworkElement)window.Content;
        var bitmap=new RenderTargetBitmap((int)content.ActualWidth,(int)content.ActualHeight,96,96,PixelFormats.Pbgra32);bitmap.Render(content);
        var png=new PngBitmapEncoder();png.Frames.Add(BitmapFrame.Create(bitmap));using var file=File.Create(Path.Combine(folder,name+".png"));png.Save(file);
    }
    public static async Task<int> Run(Window owner,string? screenshots)
    {
        foreach(var (width,height,name) in new[]{(2400,1600,"landscape"),(600,12000,"tall"),(96,210,"small")})
        {
            var bitmap=Synthetic(width,height);
            var viewer=new ImageViewerWindow(bitmap){Owner=owner,ShowActivated=false,ShowInTaskbar=false,WindowStartupLocation=WindowStartupLocation.Manual,Left=-20000,Top=0};
            try
            {
                viewer.Show();await Settle(viewer);
                var viewport=Field<ScrollViewer>(viewer,"viewport");var canvas=Field<Canvas>(viewer,"canvas");
                var image=canvas.Children.OfType<Image>().Single();
                Check(Field<bool>(viewer,"fitting") && Field<double>(viewer,"zoom")<=1,"viewer_initial_fit");
                Check(viewport.ScrollableWidth<1 && viewport.ScrollableHeight<1,"viewer_initial_image_clipped");
                if(screenshots!=null) Screenshot(viewer,screenshots,name+"-fit");
                Click(viewer,"ActualSize");await Settle(viewer);
                Check(Math.Abs(canvas.Width-width)<1 && Math.Abs(canvas.Height-height)<1,"viewer_original_dimensions");
                Click(viewer,"ZoomIn");await Settle(viewer);
                Check(Math.Abs(Field<double>(viewer,"zoom")-1.25)<.001,"viewer_zoom_in");
                Click(viewer,"ZoomOut");await Settle(viewer);
                Check(Math.Abs(Field<double>(viewer,"zoom")-1)<.001,"viewer_zoom_out");
                viewport.RaiseEvent(new MouseWheelEventArgs(Mouse.PrimaryDevice,Environment.TickCount,120){RoutedEvent=Mouse.PreviewMouseWheelEvent});
                await Settle(viewer);Check(Math.Abs(Field<double>(viewer,"zoom")-1.2)<.001,"viewer_wheel_zoom");
                Click(viewer,"ActualSize");await Settle(viewer);
                if(name=="landscape")
                {
                    var anchor=new Point(280,220);
                    var original=new Point(viewport.HorizontalOffset+anchor.X,viewport.VerticalOffset+anchor.Y);
                    Invoke(viewer,"SetZoom",2.0,(Point?)anchor);await Settle(viewer);
                    Check(Math.Abs((viewport.HorizontalOffset+anchor.X)/2-original.X)<2 && Math.Abs((viewport.VerticalOffset+anchor.Y)/2-original.Y)<2,"viewer_zoom_anchor_moved");
                    Invoke(viewer,"PanTo",new Vector(120,160));await Settle(viewer);
                    Check(Math.Abs(viewport.HorizontalOffset-120)<2 && Math.Abs(viewport.VerticalOffset-160)<2,"viewer_pan_offsets");
                    if(screenshots!=null) Screenshot(viewer,screenshots,"landscape-zoom");
                }
                Invoke(viewer,"SetZoom",100.0,null);await Settle(viewer);
                Check(Field<double>(viewer,"zoom")==8 && !Descendants(viewer).OfType<Button>().Single(b=>b.Name=="ZoomIn").IsEnabled,"viewer_zoom_limit");
                Click(viewer,"FitImage");await Settle(viewer);
                viewer.Width=600;viewer.Height=440;await Settle(viewer);
                Check(Field<bool>(viewer,"fitting") && viewport.ScrollableWidth<1 && viewport.ScrollableHeight<1,"viewer_resize_fit");
                Click(viewer,"ActualSize");await Settle(viewer);viewer.Width=800;await Settle(viewer);
                Check(!Field<bool>(viewer,"fitting") && Math.Abs(Field<double>(viewer,"zoom")-1)<.001,"viewer_manual_zoom_changed_on_resize");
                Check(ReferenceEquals(image.Source,bitmap) && bitmap.PixelWidth==width && bitmap.PixelHeight==height,"viewer_source_modified");
                var escape=viewer.InputBindings.OfType<KeyBinding>().Single(b=>b.Key==Key.Escape);
                ((RoutedCommand)escape.Command).Execute(null,viewer);await Settle(owner);
                Check(!viewer.IsVisible,"viewer_keyboard_close");
            }
            finally {viewer.Close();}
        }
        return 3;
    }
}
