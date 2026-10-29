using System.ComponentModel;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Media;
using Microsoft.Win32;

namespace ChatArchive;

public sealed class BatchExportPreferences
{
    public string[] Chats { get; set; } = [];
    public string Mode { get; set; } = "merged";

    public static BatchExportPreferences Load(string path)
    {
        try { return JsonSerializer.Deserialize<BatchExportPreferences>(File.ReadAllText(path)) ?? new(); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException) { return new(); }
    }

    public void Save(string path)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".partial";
        try
        {
            File.WriteAllText(temporary, JsonSerializer.Serialize(this));
            File.Move(temporary, path, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}

public sealed class BatchChatChoice : INotifyPropertyChanged
{
    public Chat Chat { get; }
    public string Name => Chat.Name;
    public FontFamily DisplayFont => new(Name.Contains('\u20e3') ? "Segoe UI Emoji, Microsoft YaHei UI" : "Microsoft YaHei UI");
    bool isChecked;
    public bool IsChecked
    {
        get => isChecked;
        set { if (isChecked == value) return; isChecked = value; PropertyChanged?.Invoke(this, new(nameof(IsChecked))); }
    }
    public event PropertyChangedEventHandler? PropertyChanged;
    public BatchChatChoice(Chat chat, bool selected) { Chat = chat; isChecked = selected; }
}

public sealed class BatchExportWindow : Window
{
    readonly List<BatchChatChoice> choices;
    readonly TextBox search = new();
    readonly ListBox list = new() { BorderBrush = new SolidColorBrush(Color.FromRgb(217, 226, 221)), HorizontalContentAlignment = HorizontalAlignment.Stretch };
    readonly TextBlock count = new() { TextWrapping = TextWrapping.Wrap, Foreground = Brushes.DimGray, Margin = new(0, 10, 0, 0), MaxHeight = 54 };
    readonly DatePicker start = new() { SelectedDate = DateTime.Today.AddDays(-7) };
    readonly DatePicker end = new() { SelectedDate = DateTime.Today };
    readonly RadioButton merged = new() { Content = "合并导出 · 一个 HTML 文件", GroupName = "ExportMode", Margin = new(0, 8, 0, 4) };
    readonly RadioButton separate = new() { Content = "分开导出 · 每个群聊一个 HTML", GroupName = "ExportMode", Margin = new(0, 14, 0, 4) };
    readonly TextBox folder = new() { IsReadOnly = true, TextWrapping = TextWrapping.Wrap, MaxHeight = 88, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
    readonly TextBlock error = new() { Foreground = Brushes.Firebrick, TextWrapping = TextWrapping.Wrap, VerticalAlignment = VerticalAlignment.Center };
    readonly Button export = new() { Content = "导出所选群聊", IsDefault = true, Background = new SolidColorBrush(Color.FromRgb(8, 127, 101)), Foreground = Brushes.White };
    public DateTime StartDate => start.SelectedDate!.Value.Date;
    public DateTime EndDate => end.SelectedDate!.Value.Date;
    public string[] SelectedChats => choices.Where(c => c.IsChecked).Select(c => c.Chat.Id).ToArray();
    public string Mode => merged.IsChecked == true ? "merged" : "separate";
    public string Folder => folder.Text;

    public BatchExportWindow(IReadOnlyList<Chat> chats, BatchExportPreferences preferences, string defaultFolder)
    {
        Title = "批量导出群聊"; Width = 920; Height = 700; MinWidth = 840; MinHeight = 600;
        MaxHeight = SystemParameters.WorkArea.Height; WindowStartupLocation = WindowStartupLocation.CenterOwner;
        FontFamily = new("Microsoft YaHei UI"); FontSize = 14; Background = Brushes.White;
        var remembered = (preferences.Chats ?? []).ToHashSet();
        choices = chats.Select(c => new BatchChatChoice(c, remembered.Contains(c.Id))).ToList();
        folder.Text = defaultFolder;
        merged.IsChecked = preferences.Mode != "separate";
        separate.IsChecked = preferences.Mode == "separate";
        var root = new Grid { Margin = new(28) }; Content = root;
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new());
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.Children.Add(new TextBlock { Text = "选择群聊与导出范围", FontSize = 22, FontWeight = FontWeights.SemiBold, Margin = new(0, 0, 0, 22) });
        var body = new Grid(); Grid.SetRow(body, 1); root.Children.Add(body);
        body.ColumnDefinitions.Add(new() { Width = new(1.1, GridUnitType.Star) });
        body.ColumnDefinitions.Add(new() { Width = new(28) });
        body.ColumnDefinitions.Add(new());
        var left = new DockPanel(); body.Children.Add(left);
        var searchArea = new StackPanel { Margin = new(0, 0, 0, 12) }; DockPanel.SetDock(searchArea, Dock.Top); left.Children.Add(searchArea);
        searchArea.Children.Add(new TextBlock { Text = "选择群聊", FontWeight = FontWeights.SemiBold, Margin = new(0, 0, 0, 8) });
        searchArea.Children.Add(search); search.ToolTip = "搜索群聊，已勾选项会保留";
        System.Windows.Automation.AutomationProperties.SetName(search, "搜索批量导出的群聊");
        var bottom = new StackPanel(); DockPanel.SetDock(bottom, Dock.Bottom); left.Children.Add(bottom);
        bottom.Children.Add(count);
        var clear = new Button { Content = "清空选择", HorizontalAlignment = HorizontalAlignment.Left, Padding = new(10, 5, 10, 5), Margin = new(0, 8, 0, 0) };
        clear.Click += (_, _) => { foreach (var choice in choices) choice.IsChecked = false; }; bottom.Children.Add(clear);
        ScrollViewer.SetHorizontalScrollBarVisibility(list, ScrollBarVisibility.Disabled);
        VirtualizingPanel.SetIsVirtualizing(list, true);
        var check = new FrameworkElementFactory(typeof(CheckBox));
        check.SetBinding(CheckBox.IsCheckedProperty, new Binding(nameof(BatchChatChoice.IsChecked)) { Mode = BindingMode.TwoWay, UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged });
        check.SetValue(FrameworkElement.MarginProperty, new Thickness(8, 10, 8, 10));
        check.SetBinding(ToolTipProperty, new Binding(nameof(BatchChatChoice.Name)));
        check.SetBinding(System.Windows.Automation.AutomationProperties.NameProperty, new Binding(nameof(BatchChatChoice.Name)));
        var label = new FrameworkElementFactory(typeof(TextBlock));
        label.SetBinding(TextBlock.TextProperty, new Binding(nameof(BatchChatChoice.Name)));
        label.SetBinding(TextBlock.FontFamilyProperty, new Binding(nameof(BatchChatChoice.DisplayFont)));
        label.SetValue(TextBlock.TextTrimmingProperty, TextTrimming.CharacterEllipsis);
        check.AppendChild(label); list.ItemTemplate = new DataTemplate { VisualTree = check }; left.Children.Add(list);
        var settings = new StackPanel();
        var settingsScroll = new ScrollViewer { Content = settings, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
        Grid.SetColumn(settingsScroll, 2); body.Children.Add(settingsScroll);
        settings.Children.Add(new TextBlock { Text = "统一日期范围", FontWeight = FontWeights.SemiBold });
        AddField(settings, "开始日期", start, 12); AddField(settings, "结束日期（包含当天）", end, 14);
        settings.Children.Add(new TextBlock { Text = "导出所选群聊在此期间的全部消息。", Foreground = Brushes.DimGray, FontSize = 12, TextWrapping = TextWrapping.Wrap, Margin = new(0, 8, 0, 0) });
        settings.Children.Add(new TextBlock { Text = "导出方式", FontWeight = FontWeights.SemiBold, Margin = new(0, 22, 0, 0) });
        settings.Children.Add(merged);
        settings.Children.Add(Hint("按群聊分区，包含群聊目录，区内按时间排列。"));
        settings.Children.Add(separate);
        settings.Children.Add(Hint("每个文件均包含文字、发送者、时间和本地图片。"));
        AddField(settings, "保存到", folder, 22);
        var browse = new Button { Content = "选择文件夹", HorizontalAlignment = HorizontalAlignment.Left, Margin = new(0, 8, 0, 0) };
        browse.Click += (_, _) =>
        {
            var picker = new OpenFolderDialog { Title = "选择批量导出的保存位置", InitialDirectory = Directory.Exists(Folder) ? Folder : defaultFolder };
            if (picker.ShowDialog(this) == true) folder.Text = picker.FolderName;
        };
        settings.Children.Add(browse);
        settings.Children.Add(Hint("每次新建一个批次文件夹；记住本次群聊和导出方式。"));
        var footer = new Grid { Margin = new(0, 20, 0, 0) }; Grid.SetRow(footer, 2); root.Children.Add(footer);
        footer.ColumnDefinitions.Add(new()); footer.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        footer.Children.Add(error);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal }; Grid.SetColumn(buttons, 1); footer.Children.Add(buttons);
        buttons.Children.Add(new Button { Content = "取消", IsCancel = true }); buttons.Children.Add(export);
        export.Click += (_, _) =>
        {
            if (!CanExport()) return;
            DialogResult = true;
        };
        search.TextChanged += (_, _) => ApplySearch();
        foreach (var choice in choices) choice.PropertyChanged += (_, _) => UpdateSelection();
        ApplySearch(); UpdateSelection();
    }

    static TextBlock Hint(string text) => new() { Text = text, FontSize = 12, Foreground = Brushes.DimGray, TextWrapping = TextWrapping.Wrap, Margin = new(0, 4, 0, 0) };
    static void AddField(Panel panel, string label, FrameworkElement control, int gap)
    {
        var caption = new Label { Content = label, Target = control, Padding = new(0), Margin = new(0, gap, 0, 6) };
        panel.Children.Add(caption); panel.Children.Add(control);
    }
    void ApplySearch() => list.ItemsSource = choices.Where(c => c.Name.Contains(search.Text, StringComparison.CurrentCultureIgnoreCase)).ToList();
    void UpdateSelection()
    {
        var names = choices.Where(c => c.IsChecked).Select(c => c.Name).ToArray();
        count.Text = $"已选 {names.Length} 个群聊" + (names.Length > 0 ? "：" + string.Join("、", names) : "，可搜索后勾选");
        count.FontFamily = new(count.Text.Contains('\u20e3') ? "Segoe UI Emoji, Microsoft YaHei UI" : "Microsoft YaHei UI");
        count.ToolTip = count.Text; export.IsEnabled = names.Length > 0;
    }
    bool CanExport()
    {
        error.Text = SelectedChats.Length == 0 ? "请至少选择一个群聊。"
            : start.SelectedDate == null || end.SelectedDate == null || StartDate > EndDate ? "请选择有效的日期范围。"
            : !Directory.Exists(Folder) ? "请选择存在的保存文件夹。" : "";
        return error.Text.Length == 0;
    }
}
