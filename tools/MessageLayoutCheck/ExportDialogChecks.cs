using System.IO;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using ChatArchive;

static class ExportDialogChecks
{
    static void Require(bool condition,string text) {if(!condition) throw new InvalidOperationException(text);}
    static bool Valid(ExportWindow window)=>(bool)typeof(ExportWindow).GetMethod("CanExport",BindingFlags.Instance|BindingFlags.NonPublic)!.Invoke(window,null)!;
    public static async Task<int> Run(Window owner,string? screenshots)
    {
        foreach(var selected in new[] {0,2})
        {
            var window=new ExportWindow(selected,selected>0?new DateTime(2026,10,17):null,selected>0?new DateTime(2026,10,30):null,
                "宣传部工作群（名称很长时省略显示 · 合成示例）",100)
                {Owner=owner,ShowActivated=false,ShowInTaskbar=false,Left=-20000,Top=0,WindowStartupLocation=WindowStartupLocation.Manual};
            try
            {
                window.Show();await window.Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);window.UpdateLayout();
                var start=(DatePicker)window.FindName("StartPicker");var end=(DatePicker)window.FindName("EndPicker");
                var content=(ComboBox)window.FindName("ContentPicker");var format=(ComboBox)window.FindName("FormatPicker");
                Require(window.OnlySelected==(selected>0) && Valid(window),"Export defaults are invalid");
                Require(((ComboBoxItem)content.Items[1]).IsEnabled==(selected>0),"Unavailable selection scope can be chosen");
                Require(format.Items.Count==1 && format.SelectedIndex==0,"Unexpected export formats offered");
                Require(((TextBlock)window.FindName("Summary")).Text.Contains("100") && ((TextBlock)window.FindName("Summary")).Text.Contains(selected.ToString()),"Loaded/selected summary is inaccurate");
                if(selected>0) Require(window.StartDate==new DateTime(2026,10,17) && window.EndDate==new DateTime(2026,10,30),"Selected date range lost");
                foreach(var field in new FrameworkElement[] {start,end,content,format,(Button)window.FindName("StartExportButton")})
                {
                    var surface=(FrameworkElement)window.Content;
                    var bounds=field.TransformToAncestor(surface).TransformBounds(new Rect(new Point(),field.RenderSize));
                    Require(bounds.Left>=0 && bounds.Right<=surface.ActualWidth+1 && bounds.Bottom<=surface.ActualHeight+1,"Export dialog controls clipped");
                }
                format.IsDropDownOpen=true;await window.Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
                var popup=(Popup)format.Template.FindName("PART_Popup",format);
                Require(popup.IsOpen && popup.Child.IsVisible,"Format menu cannot open");format.IsDropDownOpen=false;
                start.IsDropDownOpen=true;await window.Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
                var calendarPopup=(Popup)start.Template.FindName("PART_Popup",start);
                Require(calendarPopup.IsOpen && calendarPopup.Child.IsVisible,"Native date calendar cannot open");start.IsDropDownOpen=false;
                if(screenshots!=null) Save(window,Path.Combine(screenshots,selected>0?"export-selected.png":"export-dates.png"));
                ((Button)window.FindName("ClearDatesButton")).RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
                Require(start.SelectedDate==null && end.SelectedDate==null && !Valid(window),"Missing dates accepted");
                start.SelectedDate=new DateTime(2026,10,30);end.SelectedDate=new DateTime(2026,10,17);
                Require(!Valid(window),"Reversed dates accepted");end.SelectedDate=start.SelectedDate;
                Require(Valid(window),"Same-day export rejected");
                start.Text="not-a-date";start.RaiseEvent(new RoutedEventArgs(UIElement.LostFocusEvent));
                Require(!Valid(window),"Invalid typed date accepted");
                start.SelectedDate=new DateTime(2026,10,30);end.SelectedDate=new DateTime(2026,10,30);
                Require(Valid(window),"Correcting typed date did not recover");
                content.SelectedIndex=0;Require(!window.OnlySelected,"All-record scope did not update");
            }
            finally {window.Close();}
        }
        return 2;
    }
    static void Save(Window window,string path)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);var surface=(FrameworkElement)window.Content;
        var bitmap=new RenderTargetBitmap((int)Math.Ceiling(surface.ActualWidth),(int)Math.Ceiling(surface.ActualHeight),96,96,PixelFormats.Pbgra32);
        var visual=new DrawingVisual();
        using(var drawing=visual.RenderOpen())
        {
            drawing.DrawRectangle(Brushes.White,null,new Rect(0,0,bitmap.PixelWidth,bitmap.PixelHeight));
            drawing.DrawRectangle(new VisualBrush(surface),null,new Rect(0,0,bitmap.PixelWidth,bitmap.PixelHeight));
        }
        bitmap.Render(visual);var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var file=File.Create(path);encoder.Save(file);
    }
}
