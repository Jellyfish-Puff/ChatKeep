using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using ChatArchive;

static class FriendChatChecks
{
    const BindingFlags Flags = BindingFlags.Instance | BindingFlags.NonPublic;
    static FieldInfo Field(string name) => typeof(MainWindow).GetField(name, Flags)!;
    static void Call(MainWindow window, string name, params object?[] args) => typeof(MainWindow).GetMethod(name, Flags)!.Invoke(window, args);
    static void Require(bool value, string message) { if (!value) throw new InvalidOperationException(message); }
    static async Task Idle(MainWindow window)
    {
        for (int i = 0; i < 200 && (bool)Field("busy").GetValue(window)!; i++) await Task.Delay(20);
        Require(!(bool)Field("busy").GetValue(window)!, "Friend conversation operation timed out");
        window.UpdateLayout(); await window.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.ApplicationIdle);
    }
    static void Click(RadioButton button) { button.IsChecked = true; button.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent)); }

    public static async Task<int> Run(MainWindow window, string? screenshots)
    {
        var fixtures = new[] { new { id = "room@chatroom", name = "工作群（合成示例）", summary = "群聊消息", kind = "group" },
            new { id = "wxid_friend", name = "小林（好友示例）", summary = "明天下午一起整理材料。", kind = "friend" },
            new { id = "old_username", name = "小周（好友示例）", summary = "文件已经整理好。", kind = "friend" } };
        var start = new ProcessStartInfo("python") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true };
        start.Environment["PYTHONIOENCODING"] = "utf-8";
        start.ArgumentList.Add("-u"); start.ArgumentList.Add("-c");
        start.ArgumentList.Add("import json,sys\nchats=json.loads(sys.argv[1])\nfor line in sys.stdin:\n r=json.loads(line.lstrip('\\ufeff'))\n data={'chats':chats,'status':'合成示例 · 1 个群聊 · 2 个好友会话'} if r['action']=='connect' else [{'id':'synthetic:1','time':1794441600,'sender':'小林','self':False,'text':'明天下午一起整理材料。','image':None},{'id':'synthetic:2','time':1794441660,'sender':'我','self':True,'text':'收到，到时见。','image':None}]\n print(json.dumps({'ok':True,'data':data}),flush=True)");
        start.ArgumentList.Add(JsonSerializer.Serialize(fixtures));
        using var worker = Process.Start(start)!;
        Field("worker").SetValue(window, worker);
        var messages = (List<JsonElement>)Field("messages").GetValue(window)!;
        var selected = (HashSet<string>)Field("selected").GetValue(window)!;
        var chats = (List<Chat>)Field("chats").GetValue(window)!;
        var list = (ListBox)window.FindName("ChatList");
        var friends = (RadioButton)window.FindName("FriendChatsMenu");
        var groups = (RadioButton)window.FindName("GroupChatsMenu");
        var search = (TextBox)window.FindName("Search");
        try
        {
            ((Button)window.FindName("ConnectButton")).RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent)); await Idle(window);
            Require(list.Items.Count == 1 && ((Chat)list.Items[0]).IsGroup, "Connected group list includes friends");
            list.SelectedIndex = 0; await Idle(window);
            selected.Add("synthetic:1");
            ((ToggleButton)window.FindName("SelectionMode")).IsChecked = true;
            Click(friends); await Idle(window);
            Require(friends.IsChecked == true && groups.IsChecked == false, "Friend menu selection is not exclusive");
            Require(messages.Count == 0 && selected.Count == 0 && Field("chat").GetValue(window) == null, "Category change retains old messages or selection");
            Require(!((Button)window.FindName("ExportButton")).IsEnabled && !((Button)window.FindName("OlderButton")).IsEnabled, "Category change leaves conversation actions enabled");
            Require(list.Items.Count == 2 && list.Items.Cast<Chat>().All(c => !c.IsGroup && c.Badge == "友"), "Friend list contains groups or wrong badge");
            Require(((TextBlock)window.FindName("ConversationHeading")).Text == "好友" && Equals(search.Tag, "搜索好友"), "Friend heading or placeholder is incorrect");
            search.Text = "小周"; Require(list.Items.Count == 1 && ((Chat)list.Items[0]).Id == "old_username", "Friend name filtering failed");
            search.Clear(); list.SelectedIndex = 0; await Idle(window);
            Require((string?)Field("chat").GetValue(window) == "wxid_friend" && messages.Count == 2, "Selecting friend failed to load messages");
            ((ToggleButton)window.FindName("SelectionMode")).IsChecked = true;
            selected.Add("synthetic:1");
            ((Dictionary<string, long>)Field("selectedTimes").GetValue(window)!).Add("synthetic:1", 1794441600);
            Call(window, "RenderMessages");
            var dialog = (ExportWindow)typeof(MainWindow).GetMethod("CreateExportDialog", Flags)!.Invoke(window, null)!;
            using var request = JsonDocument.Parse(JsonSerializer.Serialize(typeof(MainWindow).GetMethod("ExportRequest", Flags)!.Invoke(window, new object[] { dialog, "synthetic.html" })));
            Require(request.RootElement.GetProperty("chat").GetString() == "wxid_friend" && request.RootElement.GetProperty("selected").GetArrayLength() == 1, "Selected friend export has wrong conversation or selection");
            dialog.Close();
            ((TextBlock)window.FindName("Notice")).Text = "好友聊天示例 · 可按日期或勾选导出";
            foreach (var width in new[] { 1380d, 960d })
            {
                window.Width = width; window.Height = width == 1380 ? 900 : 640; await Idle(window);
                Require(friends.ActualWidth >= 100 && friends.ActualHeight >= 40, "Friend menu is clipped at minimum size");
                if (screenshots != null) Save(window, Path.Combine(screenshots, width == 1380 ? "friend-chat.png" : "friend-chat-compact.png"));
            }
            var batch = new BatchExportWindow(chats.Where(c => !c.IsGroup).ToList(), new() { Chats = ["wxid_friend", "room@chatroom"] }, Path.GetTempPath(), "好友")
                { Owner = window, Left = -20000, Top = 0, ShowActivated = false, ShowInTaskbar = false, WindowStartupLocation = WindowStartupLocation.Manual };
            try
            {
                batch.Show(); batch.UpdateLayout(); await window.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.ApplicationIdle);
                Require(batch.Title == "批量导出好友" && batch.SelectedChats.SequenceEqual(new[] { "wxid_friend" }), "Friend batch settings include a group selection");
                if (screenshots != null) Save(batch, Path.Combine(screenshots, "friend-batch-settings.png"));
            }
            finally { batch.Close(); }
            Click(groups); await Idle(window);
            Require(list.Items.Count == 1 && selected.Count == 0 && messages.Count == 0 && search.Text == "", "Returning to group category keeps friend state");
            return 3;
        }
        finally
        {
            Field("worker").SetValue(window, null);
            if (!worker.HasExited) worker.Kill(true);
            Field("busy").SetValue(window, true); Field("chat").SetValue(window, null);
            Call(window, "ResetConversationTools"); chats.Clear(); messages.Clear(); Call(window, "RenderMessages");
            Field("busy").SetValue(window, false);
        }
    }
    static void Save(Window window, string path)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var content = (FrameworkElement)window.Content;
        var bitmap = new RenderTargetBitmap((int)Math.Ceiling(content.ActualWidth), (int)Math.Ceiling(content.ActualHeight), 96, 96, PixelFormats.Pbgra32);
        var visual = new DrawingVisual();
        using (var drawing = visual.RenderOpen())
        {
            var bounds = new Rect(0, 0, bitmap.PixelWidth, bitmap.PixelHeight);
            drawing.DrawRectangle(Brushes.White, null, bounds);
            drawing.DrawRectangle(new VisualBrush(content), null, bounds);
        }
        bitmap.Render(visual); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var output = File.Create(path); encoder.Save(output);
    }
}
