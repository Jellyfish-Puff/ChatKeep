using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Reflection;
using System.Security.Cryptography;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Microsoft.Win32;

namespace ChatArchive;
public record Chat(string Id, string Name, string Summary);
public partial class MainWindow : Window
{
    readonly List<Chat> chats = new();
    readonly List<JsonElement> messages = new();
    readonly HashSet<string> selected = new();
    readonly SemaphoreSlim gate = new(1);
    Process? worker;
    bool busy;
    string? chat;
    readonly string root;
    readonly bool packaged;
    public MainWindow()
    {
        InitializeComponent();
        packaged=Assembly.GetExecutingAssembly().GetManifestResourceInfo("ChatArchive.ReaderPayload")!=null;
        var folder = new DirectoryInfo(AppContext.BaseDirectory);
        if(!packaged) while (folder != null && !File.Exists(Path.Combine(folder.FullName, "src", "reader.py"))) folder = folder.Parent;
        root = packaged?AppContext.BaseDirectory:(folder?.FullName ?? AppContext.BaseDirectory);
        if (Environment.GetCommandLineArgs().Contains("--render-preview")) Loaded += (_, _) => RenderPreview();
        if (Environment.GetCommandLineArgs().Contains("--package-check")) Loaded += async (_, _) => await PackageCheck();
    }
    async Task PackageCheck()
    {
        int exit=0;
        try
        {
            var result=await Request(new {action="connect"});
            var report=new {ok=true,packaged,groups=result.GetProperty("chats").GetArrayLength(),externalPythonRequired=!packaged};
            Directory.CreateDirectory(Path.Combine(root,"private"));
            await File.WriteAllTextAsync(Path.Combine(root,"private","package-check.json"),JsonSerializer.Serialize(report));
        }
        catch(Exception ex)
        {
            exit=1; Directory.CreateDirectory(Path.Combine(root,"private"));
            await File.WriteAllTextAsync(Path.Combine(root,"private","package-check.json"),JsonSerializer.Serialize(new {ok=false,error=ex.Message}));
        }
        Close();Application.Current.Shutdown(exit);
    }
    string ExtractReader()
    {
        using var resource=Assembly.GetExecutingAssembly().GetManifestResourceStream("ChatArchive.ReaderPayload") ?? throw new Exception("缺少内置读取模块。");
        var hash=Convert.ToHexString(SHA256.HashData(resource));resource.Position=0;
        var directory=Path.Combine(root,"private","runtime");Directory.CreateDirectory(directory);
        var executable=Path.Combine(directory,"ChatReader-"+hash[..16]+".exe");
        if(File.Exists(executable))
        {
            using var file=File.OpenRead(executable);
            if(Convert.ToHexString(SHA256.HashData(file))==hash) return executable;
        }
        var temporary=executable+"."+Guid.NewGuid().ToString("N")+".tmp";
        try
        {
            using(var output=File.Create(temporary)) resource.CopyTo(output);
            File.Move(temporary,executable,true);
        }
        finally { if(File.Exists(temporary)) File.Delete(temporary); }
        return executable;
    }
    void RenderPreview()
    {
        if(Environment.GetCommandLineArgs().Contains("--compact-preview")) {Width=MinWidth;Height=MinHeight;}
        var previewUrl="https://mp.weixin.qq.com/s?__biz=synthetic-campus&mid=123456789&idx=1&sn=example-only&scene=1&sharer_shareinfo=synthetic-preview";
        var previewChat=new Chat("preview","项目协作群（界面示例）","下周的工作安排已更新");
        chats.Add(previewChat);ApplySearch();ChatTitle.Text=previewChat.Name;Status.Text="界面预览 · 合成示例";GroupCount.Text="群聊列表";
        var previewMessages=new[] {
            new {id="1",time=1792249200,sender="张同学",self=false,text="[公众号文章]\n标题：校园摄影大赛征稿通知\n公众号：校园宣传部\n链接："+previewUrl,image=(string?)null},
            new {id="2",time=1792249260,sender="李同学",self=false,text="[引用回复]\n这篇推文的排版可以参考，周三前整理好初稿。\n引用 张同学：\n[公众号文章]\n标题：校园摄影大赛征稿通知\n链接："+previewUrl,image=(string?)null},
            new {id="3",time=1792249320,sender="我",self=true,text="收到，我来整理摄影大赛的宣传安排。",image=(string?)null},
            new {id="4",time=1792249380,sender="张同学",self=false,text="[拍一拍]\n张同学 拍了拍 我",image=(string?)null}
        };
        using(var doc=JsonDocument.Parse(JsonSerializer.Serialize(previewMessages))) messages.AddRange(doc.RootElement.EnumerateArray().Select(m=>m.Clone()));
        if(Environment.GetCommandLineArgs().Contains("--image-preview"))
        {
            var visual=new DrawingVisual();
            using(var drawing=visual.RenderOpen())
            {
                drawing.DrawRectangle(Brushes.White,null,new Rect(0,0,960,540));
                drawing.DrawRectangle(new SolidColorBrush(Color.FromRgb(10,155,125)),null,new Rect(24,24,912,160));
                drawing.DrawText(new FormattedText("宣传部工作安排 · 合成图片",System.Globalization.CultureInfo.CurrentCulture,FlowDirection.LeftToRight,new Typeface("Microsoft YaHei"),42,Brushes.White,1),new Point(48,70));
                drawing.DrawText(new FormattedText("一、整理摄影大赛宣传文案\n二、周三前确认排版与配图\n三、导出时保留图片像素尺寸",System.Globalization.CultureInfo.CurrentCulture,FlowDirection.LeftToRight,new Typeface("Microsoft YaHei"),32,Brushes.Black,1),new Point(48,240));
            }
            var preview=new RenderTargetBitmap(960,540,96,96,PixelFormats.Pbgra32);preview.Render(visual);
            var png=new PngBitmapEncoder();png.Frames.Add(BitmapFrame.Create(preview));using var encoded=new MemoryStream();png.Save(encoded);
            using var imageDoc=JsonDocument.Parse(JsonSerializer.Serialize(new {id="0",time=1792249140,sender="张同学",self=false,text="[图片]",image="data:image/png;base64,"+Convert.ToBase64String(encoded.ToArray()),imageWidth=960,imageQuality="large",imageNote="本地大图 · 960 × 540 像素（合成示例）"}));
            messages.Insert(0,imageDoc.RootElement.Clone());
        }
        RenderMessages();Notice.Text="界面示例使用合成消息。实际内容由本机微信读取。";
        UpdateLayout(); var surface=(FrameworkElement)Content;
        var bitmap = new RenderTargetBitmap((int)surface.ActualWidth, (int)surface.ActualHeight, 96, 96, PixelFormats.Pbgra32);
        bitmap.Render(surface); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
        Directory.CreateDirectory(Path.Combine(root,"docs")); using(var f=File.Create(Path.Combine(root,"docs","interface-preview.png"))) encoder.Save(f);
        Close();
    }
    async Task<JsonElement> Request(object data, Action<JsonElement>? progress=null)
    {
        await gate.WaitAsync();
        try
        {
            if(worker == null || worker.HasExited)
            {
                var executable=packaged?ExtractReader():"python";
                var arguments=packaged?"--serve":"-u -X utf8 \"" + Path.Combine(root,"src","reader.py") + "\" --serve";
                var start = new ProcessStartInfo(executable,arguments) { RedirectStandardInput=true, RedirectStandardOutput=true, RedirectStandardError=true, CreateNoWindow=true, UseShellExecute=false, WorkingDirectory=root, StandardInputEncoding=new UTF8Encoding(false), StandardOutputEncoding=Encoding.UTF8, StandardErrorEncoding=Encoding.UTF8 };
                start.Environment["CHATARCHIVE_DATA_ROOT"]=root;
                start.Environment["PYTHONIOENCODING"]="utf-8";
                worker = Process.Start(start) ?? throw new Exception("无法启动本地读取模块。");
                worker.ErrorDataReceived += (_,_) => { }; worker.BeginErrorReadLine();
            }
            await worker.StandardInput.WriteLineAsync(JsonSerializer.Serialize(data)); await worker.StandardInput.FlushAsync();
            while(true)
            {
                var line=await worker.StandardOutput.ReadLineAsync() ?? throw new Exception("读取模块已退出，请重新连接。");
                using var doc=JsonDocument.Parse(line); var result=doc.RootElement;
                if(result.TryGetProperty("event",out var kind) && kind.GetString()=="progress")
                {
                    progress?.Invoke(result.GetProperty("data"));
                    continue;
                }
                if(!result.GetProperty("ok").GetBoolean()) throw new Exception(result.GetProperty("error").GetString());
                return result.GetProperty("data").Clone();
            }
        }
        finally { gate.Release(); }
    }
    void SetBusy(bool value, string? notice=null)
    {
        busy=value; ConnectButton.IsEnabled=!value; ChatList.IsEnabled=!value; Search.IsEnabled=!value;
        BatchExportButton.IsEnabled=!value && chats.Count>0;
        ExportButton.IsEnabled=!value && chat!=null; OlderButton.IsEnabled=!value && messages.Count>0; SelectionMode.IsEnabled=!value;
        if(notice!=null) Notice.Text=notice;
    }
    async void ConnectClick(object sender,RoutedEventArgs e)
    {
        SetBusy(true,"正在连接微信并校验本地数据，请稍候……");
        try
        {
            var result=await Request(new {action="connect"}); chats.Clear(); messages.Clear(); selected.Clear(); chat=null; MessagePanel.Children.Clear(); ChatTitle.Text="选择一个群聊";
            foreach(var item in result.GetProperty("chats").EnumerateArray()) chats.Add(new(item.GetProperty("id").GetString()!,item.GetProperty("name").GetString()!,item.GetProperty("summary").GetString()!));
            Status.Text=result.GetProperty("status").GetString(); GroupCount.Text=$"{chats.Count} 个群聊 · 支持搜索"; ApplySearch();
            Notice.Text="已连接，请选择一个群聊。首次打开会校验消息副本，可能需要一些时间。";
        }
        catch(Exception ex) { ShowError(ex); }
        finally { SetBusy(false); }
    }
    void SearchChanged(object sender,TextChangedEventArgs e) { if(ChatList!=null) ApplySearch(); }
    void ApplySearch() => ChatList.ItemsSource=chats.Where(c=>c.Name.Contains(Search.Text,StringComparison.CurrentCultureIgnoreCase)).ToList();
    async void ChatChanged(object sender,SelectionChangedEventArgs e)
    {
        if(busy || ChatList.SelectedItem is not Chat item || item.Id==chat) return;
        chat=item.Id; ChatTitle.Text=item.Name; messages.Clear(); selected.Clear(); RenderMessages();
        await LoadMessages(false);
    }
    async Task LoadMessages(bool older)
    {
        if(chat==null) return;
        SetBusy(true,older?"正在加载更早消息……":"正在读取消息……");
        try
        {
            long? before=older && messages.Count>0?messages.Min(m=>m.GetProperty("time").GetInt64()):null;
            var result=await Request(new {action="messages",chat,before}); var incoming=result.EnumerateArray().Select(m=>m.Clone()).ToList();
            var ids=messages.Select(m=>m.GetProperty("id").GetString()).ToHashSet(); messages.InsertRange(0,incoming.Where(m=>!ids.Contains(m.GetProperty("id").GetString())));
            RenderMessages(); Notice.Text=incoming.Count==0?"该范围没有更多消息。":$"已显示 {messages.Count} 条消息。勾选消息可导出所选内容，也可直接按日期导出。";
            if(!older) MessagesScroll.ScrollToBottom();
        }
        catch(Exception ex) { ShowError(ex); }
        finally { SetBusy(false); }
    }
    async void OlderClick(object sender,RoutedEventArgs e) => await LoadMessages(true);
    void SelectionChanged(object sender,RoutedEventArgs e) { RenderMessages(); }
    void RenderMessages()
    {
        MessagePanel.Children.Clear();
        foreach(var message in messages)
        {
            var id=message.GetProperty("id").GetString()!; var self=message.GetProperty("self").GetBoolean();
            var line=new Grid {Margin=new Thickness(0,10,0,10)}; line.ColumnDefinitions.Add(new(){Width=GridLength.Auto}); line.ColumnDefinitions.Add(new());
            var check=new CheckBox {IsChecked=selected.Contains(id),Visibility=SelectionMode.IsChecked==true?Visibility.Visible:Visibility.Collapsed,VerticalAlignment=VerticalAlignment.Center,Margin=new Thickness(0,0,12,0)};
            System.Windows.Automation.AutomationProperties.SetName(check,"选择这条消息");
            check.Checked+=(_,_)=>{selected.Add(id);UpdateCount();}; check.Unchecked+=(_,_)=>{selected.Remove(id);UpdateCount();}; line.Children.Add(check);
            var stack=new StackPanel {HorizontalAlignment=self?HorizontalAlignment.Right:HorizontalAlignment.Left,MaxWidth=570}; Grid.SetColumn(stack,1); line.Children.Add(stack);
            stack.Children.Add(new TextBlock {Text=message.GetProperty("sender").GetString()+" · "+DateTimeOffset.FromUnixTimeSeconds(message.GetProperty("time").GetInt64()).ToLocalTime().ToString("MM-dd HH:mm"),Foreground=new SolidColorBrush(Color.FromRgb(82,102,91)),FontSize=12,Margin=new Thickness(0,0,0,6)});
            UIElement body;
            if(message.GetProperty("image").ValueKind==JsonValueKind.String)
            {
                var uri=message.GetProperty("image").GetString()!; using var stream=new MemoryStream(Convert.FromBase64String(uri[(uri.IndexOf(',')+1)..]));
                var bmp=new BitmapImage(); bmp.BeginInit();bmp.CacheOption=BitmapCacheOption.OnLoad;
                if(message.TryGetProperty("imageWidth",out var width) && width.GetInt32()>0) bmp.DecodePixelWidth=Math.Min(680,width.GetInt32());
                bmp.StreamSource=stream;bmp.EndInit();bmp.Freeze();
                var picture=new StackPanel();picture.Children.Add(new Image {Source=bmp,MaxWidth=340,MaxHeight=300,Stretch=Stretch.Uniform});
                if(message.TryGetProperty("imageNote",out var note) && !string.IsNullOrEmpty(note.GetString())) picture.Children.Add(new TextBlock{Text=note.GetString(),TextWrapping=TextWrapping.Wrap,MaxWidth=340,FontSize=11,Foreground=Brushes.DimGray,Margin=new Thickness(0,6,0,0)});
                if(message.TryGetProperty("imageQuality",out var quality) && quality.GetString() is "image" or "large")
                {
                    var view=new Button {Content="查看大图",HorizontalAlignment=HorizontalAlignment.Left,Margin=new Thickness(0,8,0,0),Padding=new Thickness(12,6,12,6)};
                    view.Click+=(_,_)=>ShowFullImage(uri);picture.Children.Add(view);
                }
                body=picture;
            }
            else
            {
                var content=new TextBox {Text=message.GetProperty("text").GetString() ?? "",IsReadOnly=true,IsReadOnlyCaretVisible=true,IsUndoEnabled=false,TextWrapping=TextWrapping.Wrap,Foreground=new SolidColorBrush(Color.FromRgb(32,44,37)),Background=Brushes.Transparent,BorderThickness=new Thickness(0),Padding=new Thickness(0),MaxWidth=530,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,VerticalScrollBarVisibility=ScrollBarVisibility.Disabled};
                // Font fallback for keycap emoji can make WPF measure/render disagree,
                // terminating the process. Prefer the installed emoji font explicitly.
                if(content.Text.Contains('\u20e3')) content.FontFamily=new FontFamily("Segoe UI Emoji, Microsoft YaHei UI");
                System.Windows.Automation.AutomationProperties.SetName(content,"消息内容，可选择并复制");
                body=content;
            }
            stack.Children.Add(new Border {Child=body,Background=new SolidColorBrush((Color)ColorConverter.ConvertFromString(self?"#D9F2DC":"#FFFFFF")),CornerRadius=new CornerRadius(8),Padding=new Thickness(14,10,14,10)});
            MessagePanel.Children.Add(line);
        }
        UpdateCount();
    }
    void UpdateCount() => SelectionCount.Text=selected.Count==0?"未选择消息":$"已选择 {selected.Count} 条消息";
    void ShowFullImage(string uri)
    {
        try
        {
            using var stream=new MemoryStream(Convert.FromBase64String(uri[(uri.IndexOf(',')+1)..]));
            var bitmap=new BitmapImage();bitmap.BeginInit();bitmap.CacheOption=BitmapCacheOption.OnLoad;bitmap.StreamSource=stream;bitmap.EndInit();bitmap.Freeze();
            new ImageViewerWindow(bitmap) {Owner=this}.Show();
        }
        catch(Exception ex) {ShowError(ex);}
    }
    async void ExportClick(object sender,RoutedEventArgs e)
    {
        if(chat==null) return;
        var chosen=messages.Where(m=>selected.Contains(m.GetProperty("id").GetString()!)).ToList();
        DateTime? selectedStart=chosen.Count>0?DateTimeOffset.FromUnixTimeSeconds(chosen.Min(m=>m.GetProperty("time").GetInt64())).LocalDateTime.Date:null;
        DateTime? selectedEnd=chosen.Count>0?DateTimeOffset.FromUnixTimeSeconds(chosen.Max(m=>m.GetProperty("time").GetInt64())).LocalDateTime.Date:null;
        var dialog=new ExportWindow(selected.Count,selectedStart,selectedEnd) {Owner=this}; if(dialog.ShowDialog()!=true) return;
        string folder=Path.Combine(root,"exports"); Directory.CreateDirectory(folder);
        var safe=string.Concat(ChatTitle.Text.Select(c=>Path.GetInvalidFileNameChars().Contains(c)?'_':c));
        var picker=new SaveFileDialog {Filter="HTML 聊天记录 (*.html)|*.html",InitialDirectory=folder,FileName=$"{safe}_{dialog.StartDate:yyyyMMdd}_{dialog.EndDate:yyyyMMdd}.html",AddExtension=true,DefaultExt=".html"};
        if(picker.ShowDialog(this)!=true) return;
        SetBusy(true,"正在导出文字和本地图片，请稍候……");
        try
        {
            var result=await Request(new {action="export",chat,start=dialog.StartDate.ToString("yyyy-MM-dd"),end=dialog.EndDate.ToString("yyyy-MM-dd"),selected=dialog.OnlySelected?selected.ToArray():null,path=picker.FileName});
            var count=result.GetProperty("count").GetInt32();var missing=result.GetProperty("missingImages").GetInt32();
            var thumbnails=result.GetProperty("thumbnailImages").GetInt32();
            Notice.Text=$"已导出 {count} 条消息，图片已嵌入 HTML。"+(thumbnails>0?$"{thumbnails} 张使用缩略图，文件内已标注。":"")+(missing>0?$"{missing} 张图片缺失或无法解码。":"");
            Process.Start(new ProcessStartInfo("explorer.exe","/select,\""+picker.FileName+"\""){UseShellExecute=true});
        }
        catch(Exception ex) {ShowError(ex);}
        finally {SetBusy(false);}
    }
    async void BatchExportClick(object sender,RoutedEventArgs e)
    {
        if(busy || chats.Count==0) return;
        try
        {
            var folder=Path.Combine(root,"exports");Directory.CreateDirectory(folder);
            var preferencesPath=Path.Combine(root,"private","batch-export.json");
            var dialog=new BatchExportWindow(chats,BatchExportPreferences.Load(preferencesPath),folder) {Owner=this};
            if(dialog.ShowDialog()!=true) return;
            var warning="";
            try { new BatchExportPreferences {Chats=dialog.SelectedChats,Mode=dialog.Mode}.Save(preferencesPath); }
            catch(Exception ex) when(ex is IOException or UnauthorizedAccessException) {warning="本次导出仍可进行，但未能保存上次选择设置。";}
            SetBusy(true,"正在准备批量导出文字和本地图片……");
            var result=await Request(new {action="export_batch",chats=dialog.SelectedChats,mode=dialog.Mode,
                start=dialog.StartDate.ToString("yyyy-MM-dd"),end=dialog.EndDate.ToString("yyyy-MM-dd"),folder=dialog.Folder},
                p=>Notice.Text=$"正在导出第 {p.GetProperty("index").GetInt32()} / {p.GetProperty("total").GetInt32()} 个群聊：{p.GetProperty("name").GetString()}……");
            var groups=result.GetProperty("results").EnumerateArray().ToList();
            Notice.Text=$"批量导出完成：{groups.Count(g=>g.GetProperty("status").GetString()=="exported")} 个群聊，{result.GetProperty("count").GetInt32()} 条消息；"
                +$"{groups.Count(g=>g.GetProperty("status").GetString()=="empty")} 个群聊无消息，{groups.Count(g=>g.GetProperty("status").GetString()=="failed")} 个失败。";
            new BatchExportResultWindow(result,warning) {Owner=this}.ShowDialog();
        }
        catch(Exception ex) {ShowError(ex);}
        finally {SetBusy(false);}
    }
    void ShowError(Exception ex) {Notice.Text="操作未完成："+ex.Message;MessageBox.Show(this,ex.Message,"聊存 ChatKeep",MessageBoxButton.OK,MessageBoxImage.Information);}
    void OpenExports(object sender,RoutedEventArgs e) {var p=Path.Combine(root,"exports");Directory.CreateDirectory(p);Process.Start(new ProcessStartInfo(p){UseShellExecute=true});}
    void WindowClosing(object? sender,System.ComponentModel.CancelEventArgs e) {if(worker is {HasExited:false}) worker.Kill(true);worker?.Dispose();}
}
