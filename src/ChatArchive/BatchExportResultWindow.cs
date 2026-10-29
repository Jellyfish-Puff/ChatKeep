using System.Diagnostics;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace ChatArchive;

public sealed class BatchExportResultWindow : Window
{
    public BatchExportResultWindow(JsonElement result, string warning = "")
    {
        Title = "批量导出结果"; Width = 640; Height = 560; MinWidth = 500; MinHeight = 400;
        MaxHeight = SystemParameters.WorkArea.Height; WindowStartupLocation = WindowStartupLocation.CenterOwner;
        FontFamily = new("Microsoft YaHei UI"); FontSize = 14; Background = Brushes.White;
        var root = new DockPanel { Margin = new(28) }; Content = root;
        var title = new TextBlock { Text = "批量导出结果", FontSize = 22, FontWeight = FontWeights.SemiBold, Margin = new(0, 0, 0, 18) };
        DockPanel.SetDock(title, Dock.Top); root.Children.Add(title);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new(0, 18, 0, 0) };
        DockPanel.SetDock(buttons, Dock.Bottom); root.Children.Add(buttons);
        var folder = result.GetProperty("folder").GetString();
        if (folder != null)
        {
            var open = new Button { Content = "打开导出文件夹" }; buttons.Children.Add(open);
            open.Click += (_, _) =>
            {
                try { Process.Start(new ProcessStartInfo(folder) { UseShellExecute = true }); }
                catch (Exception) { MessageBox.Show(this, "无法打开文件夹，请从结果中复制保存位置。", Title); }
            };
        }
        var close = new Button { Content = "完成", IsDefault = true, IsCancel = true }; buttons.Children.Add(close);
        close.Click += (_, _) => Close();
        var groups = result.GetProperty("results").EnumerateArray().ToList();
        var lines = new List<string>
        {
            $"已导出 {groups.Count(g => g.GetProperty("status").GetString() == "exported")} / {groups.Count} 个群聊，共 {result.GetProperty("count").GetInt32()} 条消息。",
            $"缩略图：{result.GetProperty("thumbnailImages").GetInt32()} 张；缺失或无法解码：{result.GetProperty("missingImages").GetInt32()} 张。",
            ""
        };
        foreach (var group in groups)
        {
            var detail = group.GetProperty("status").GetString() switch
            {
                "exported" => $"已导出 {group.GetProperty("count").GetInt32()} 条消息",
                "empty" => "所选日期范围没有消息",
                _ => "导出失败：" + group.GetProperty("error").GetString()
            };
            lines.Add(group.GetProperty("name").GetString() + "：" + detail);
        }
        lines.Add("");
        lines.Add(folder != null ? "保存位置：\n" + folder : "本次未生成 HTML 文件，请查看各群聊结果。");
        if (warning.Length > 0) lines.Add("\n" + warning);
        var content = new TextBox { Text = string.Join("\n", lines), IsReadOnly = true, IsReadOnlyCaretVisible = true, IsUndoEnabled = false,
            TextWrapping = TextWrapping.Wrap, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, BorderThickness = new(0), Padding = new(0) };
        if (content.Text.Contains('\u20e3')) content.FontFamily = new("Segoe UI Emoji, Microsoft YaHei UI");
        System.Windows.Automation.AutomationProperties.SetName(content, "批量导出各群聊结果与保存位置，可选择复制");
        root.Children.Add(content);
    }
}
