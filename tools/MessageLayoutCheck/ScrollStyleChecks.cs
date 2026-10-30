using System.Reflection;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using System.IO;
using ChatArchive;

static class ScrollStyleChecks
{
    const BindingFlags Flags = BindingFlags.Instance | BindingFlags.NonPublic;
    static void Require(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
    static async Task Settle(Window window)
    {
        window.UpdateLayout(); await window.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.ApplicationIdle);
        window.UpdateLayout();
    }
    static IEnumerable<DependencyObject> Descendants(DependencyObject root)
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++)
        {
            var child = VisualTreeHelper.GetChild(root, i); yield return child;
            foreach (var nested in Descendants(child)) yield return nested;
        }
    }
    static ScrollBar Bar(ScrollViewer viewer) => (ScrollBar)viewer.Template.FindName("PART_VerticalScrollBar", viewer)!;
    static Track Track(ScrollBar bar) => (Track)bar.Template.FindName("PART_Track", bar)!;
    static void CheckProportion(ScrollViewer viewer)
    {
        var bar = Bar(viewer); var track = Track(bar);
        var expected = Math.Max(24, track.ActualHeight * bar.ViewportSize / (bar.Maximum - bar.Minimum + bar.ViewportSize));
        Require(bar.IsVisible && Math.Abs(bar.ActualWidth - 12) < .1, "Slim scrollbar is missing or has the wrong hit width");
        Require(Math.Abs(track.Thumb.ActualHeight - expected) < 1, "Thumb length does not follow visible content proportion");
        Require(Descendants(bar).OfType<RepeatButton>().Count() == 2, "Scrollbar still includes arrow buttons");
    }
    static async Task CheckScrollActions(MainWindow window, ScrollViewer viewer)
    {
        viewer.ScrollToTop(); await Settle(window);
        var bar = Bar(viewer);
        ScrollBar.PageDownCommand.Execute(null, bar); await Settle(window);
        Require(viewer.VerticalOffset > 0, "Scrollbar page command no longer scrolls");
        viewer.ScrollToTop(); await Settle(window);
        var thumb = Track(bar).Thumb;
        thumb.RaiseEvent(new DragStartedEventArgs(0, 0) { RoutedEvent = Thumb.DragStartedEvent });
        thumb.RaiseEvent(new DragDeltaEventArgs(0, 35) { RoutedEvent = Thumb.DragDeltaEvent });
        thumb.RaiseEvent(new DragCompletedEventArgs(0, 35, false) { RoutedEvent = Thumb.DragCompletedEvent });
        await Settle(window);
        Require(viewer.VerticalOffset > 0, "Dragging slim thumb no longer scrolls");
        viewer.ScrollToBottom(); await Settle(window);
        Require(Math.Abs(viewer.VerticalOffset - viewer.ScrollableHeight) < 1, "Cannot reach the end of content");
    }
    public static async Task<int> Run(MainWindow window, string? screenshots)
    {
        var list = (ListBox)window.FindName("ChatList");
        var scroll = (ScrollViewer)window.FindName("MessagesScroll");
        var panel = (StackPanel)window.FindName("MessagePanel");
        var chats = (List<Chat>)typeof(MainWindow).GetField("chats", Flags)!.GetValue(window)!;
        var messages = (List<JsonElement>)typeof(MainWindow).GetField("messages", Flags)!.GetValue(window)!;
        // Prevent native selection events from launching the reader; all fixture data is synthetic.
        typeof(MainWindow).GetField("busy", Flags)!.SetValue(window, true);
        try
        {
            window.Width = 1380; window.Height = 900;
            chats.Clear();
            var labels = new[] { "宣传部工作群", "新媒体日常协作群", "摄影与视频协作群", "公众号推文审核群", "部门活动统筹群" };
            for (var i = 0; i < 60; i++) chats.Add(new("synthetic-" + i, labels[i % labels.Length] + "（合成示例）", "工作安排已更新，请按时间完成。"));
            typeof(MainWindow).GetMethod("ApplySearch", Flags)!.Invoke(window, null);
            var search = (TextBox)window.FindName("Search");
            search.Text = "摄影"; await Settle(window);
            Require(list.Items.Count == 12, "Restyled search no longer filters group names");
            search.SelectAll();
            Require(search.SelectedText == "摄影", "Restyled search lost native text selection");
            search.Text = new string('长', 150); await Settle(window);
            Require(list.Items.Count == 0 && search.Text.Length == 150, "Long search text changes or stops filtering");
            search.Clear(); await Settle(window);
            Require(list.Items.Count == 60 && search.Text == "", "Clearing search does not restore groups");
            list.SelectedIndex = 1;
            panel.Children.Clear(); panel.Children.Add(new Border { Height = 1600, Background = Brushes.White });
            await Settle(window);
            var listScroll = Descendants(list).OfType<ScrollViewer>().First();
            CheckProportion(listScroll); CheckProportion(scroll);
            var oldLength = Track(Bar(scroll)).Thumb.ActualHeight;
            ((FrameworkElement)panel.Children[0]).Height = 5000; await Settle(window);
            CheckProportion(scroll);
            Require(Track(Bar(scroll)).Thumb.ActualHeight < oldLength, "Longer content did not shorten the thumb");
            ((FrameworkElement)panel.Children[0]).Height = 1000000; await Settle(window);
            CheckProportion(scroll);
            Require(Math.Abs(Track(Bar(scroll)).Thumb.ActualHeight - 24) < 1, "Very long content loses minimum draggable thumb size");
            ((FrameworkElement)panel.Children[0]).Height = 5000; await Settle(window);
            await CheckScrollActions(window, listScroll); await CheckScrollActions(window, scroll);
            var item = (ListBoxItem)list.ItemContainerGenerator.ContainerFromIndex(list.SelectedIndex);
            // Bring a virtualized selected item back before inspecting its visual state.
            list.ScrollIntoView(list.SelectedItem); await Settle(window);
            item = (ListBoxItem)list.ItemContainerGenerator.ContainerFromIndex(list.SelectedIndex);
            var row = (Border)item.Template.FindName("RowBackground", item)!;
            Require(row.CornerRadius.TopLeft > 0 && ((SolidColorBrush)row.Background).Color == (Color)ColorConverter.ConvertFromString("#E1F1E9"), "Selected row lost its rounded background");
            var selectedColor = ((SolidColorBrush)row.Background).Color;
            ((TextBox)window.FindName("Search")).Focus(); await Settle(window);
            Require(((SolidColorBrush)row.Background).Color == selectedColor, "Inactive selection changed back to a system rectangle");
            panel.Children.Clear(); panel.Children.Add(new Border { Height = 30 });
            await Settle(window);
            Require(scroll.ComputedVerticalScrollBarVisibility == Visibility.Collapsed, "Scrollbar remains visible when content fits");
            messages.Clear();
            for (var i = 0; i < 30; i++)
            {
                using var doc = JsonDocument.Parse(JsonSerializer.Serialize(new { id = "synthetic-" + i, time = 1793271600 + i * 120,
                    sender = i % 3 == 1 ? "我" : "合成示例", self = i % 3 == 1,
                    text = new[] { "周五活动的宣传安排已更新，大家可以在这里确认分工。", "收到，我来整理文案和配图。", "请在今晚前确认推文初稿，明天一起检查排版。" }[i % 3], image = (string?)null }));
                messages.Add(doc.RootElement.Clone());
            }
            typeof(MainWindow).GetMethod("RenderMessages", Flags)!.Invoke(window, null);
            ((TextBlock)window.FindName("ChatTitle")).Text = "新媒体日常协作群（合成示例）";
            ((TextBlock)window.FindName("GroupCount")).Text = "60 个群聊 · 合成界面示例";
            ((TextBlock)window.FindName("Notice")).Text = "圆角选中与细滚动条预览 · 全部为合成消息。";
            foreach (var size in new[] { new Size(1380, 900), new Size(window.MinWidth, 640) })
            {
                window.Width = size.Width; window.Height = size.Height;
                listScroll.ScrollToTop(); scroll.ScrollToTop(); await Settle(window);
                CheckProportion(listScroll); CheckProportion(scroll);
                if (screenshots != null) Save(window, Path.Combine(screenshots, size.Width == 1380 ? "rounded-chat-and-scrollbars.png" : "rounded-chat-and-scrollbars-compact.png"));
            }
            chats.Clear(); typeof(MainWindow).GetMethod("ApplySearch", Flags)!.Invoke(window, null); await Settle(window);
            Require(listScroll.ComputedVerticalScrollBarVisibility == Visibility.Collapsed, "Empty group list shows scrollbar");
            return 2;
        }
        finally
        {
            chats.Clear(); messages.Clear(); panel.Children.Clear();
            typeof(MainWindow).GetField("busy", Flags)!.SetValue(window, false);
        }
    }
    static void Save(Window window, string path)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var content = (FrameworkElement)window.Content;
        var bitmap = new RenderTargetBitmap((int)Math.Ceiling(content.ActualWidth), (int)Math.Ceiling(content.ActualHeight), 96, 96, PixelFormats.Pbgra32);
        var visual = new DrawingVisual();
        using (var drawing = visual.RenderOpen()) drawing.DrawRectangle(new VisualBrush(content), null, new Rect(0, 0, bitmap.PixelWidth, bitmap.PixelHeight));
        bitmap.Render(visual); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var output = File.Create(path); encoder.Save(output);
    }
}
