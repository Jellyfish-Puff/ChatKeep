using System.Reflection;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using System.Windows.Media;
using ChatArchive;

// Payload enters through stdin only. Never log text, identifiers, or image bytes.
class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        using var document=JsonDocument.Parse(Console.In.ReadToEnd());
        var payload=document.RootElement.EnumerateArray().Select(x=>x.Clone()).ToList();
        var app=new App();app.InitializeComponent();
        var window=new MainWindow {Left=-20000,Top=0,ShowActivated=false,ShowInTaskbar=false};
        var flags=BindingFlags.Instance|BindingFlags.NonPublic;
        var messages=(List<JsonElement>)typeof(MainWindow).GetField("messages",flags)!.GetValue(window)!;
        var render=typeof(MainWindow).GetMethod("RenderMessages",flags)!;
        var scroll=(ScrollViewer)window.FindName("MessagesScroll");
        var selection=(CheckBox)window.FindName("SelectionMode");
        window.Loaded+=async (_,_)=>
        {
            try
            {
                for(var cycle=0;cycle<6;cycle++)
                {
                    messages.Clear();messages.AddRange(payload);
                    selection.IsChecked=cycle%2==1;
                    render.Invoke(window,null);
                    window.Width=cycle%2==0?1380:1024;
                    window.Height=cycle%2==0?900:640;
                    window.UpdateLayout();scroll.ScrollToBottom();
                    await window.Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
                    await Task.Delay(100);
                    var panel=(StackPanel)window.FindName("MessagePanel");
                    var textBoxes=Descendants(panel).OfType<TextBox>().Where(t=>t.IsReadOnly).ToList();
                    var expected=payload.Where(m=>m.GetProperty("image").ValueKind!=JsonValueKind.String).Select(m=>m.GetProperty("text").GetString() ?? "").ToList();
                    if(!textBoxes.Select(t=>t.Text).SequenceEqual(expected)) throw new InvalidOperationException("Text changed during display");
                    int expectedButtons=payload.Count(m=>m.GetProperty("image").ValueKind==JsonValueKind.String && m.TryGetProperty("imageQuality",out var q) && q.GetString() is "image" or "large");
                    if(Descendants(panel).OfType<Button>().Count(b=>Equals(b.Content,"查看大图"))!=expectedButtons) throw new InvalidOperationException("Image quality buttons incorrect");
                    foreach(var textBox in textBoxes)
                    {
                        textBox.SelectAll();
                        if(textBox.SelectedText!=textBox.Text || textBox.ActualWidth>530.1) throw new InvalidOperationException("Selection or wrapping failed");
                        textBox.Select(0,0);
                    }
                    scroll.ScrollToTop();window.UpdateLayout();
                    messages.Clear();render.Invoke(window,null);
                    await Task.Delay(50);
                }
                var viewerCases=await ImageViewerChecks.Run(window,args.FirstOrDefault());
                var batchCases=await BatchExportChecks.Run(window,args.FirstOrDefault());
                Console.WriteLine(JsonSerializer.Serialize(new {ok=true,messages=payload.Count,cycles=6,viewerCases,batchCases}));
                window.Close();Dispatcher.CurrentDispatcher.BeginInvokeShutdown(DispatcherPriority.Background);
            }
            catch(Exception ex)
            {
                Console.WriteLine(JsonSerializer.Serialize(new {ok=false,errorType=ex.GetType().Name,check=ex is InvalidOperationException?ex.Message:"unexpected_error"}));
                Environment.ExitCode=1;
                window.Close();Dispatcher.CurrentDispatcher.BeginInvokeShutdown(DispatcherPriority.Background);
            }
        };
        window.Show();Dispatcher.Run();
        return Environment.ExitCode;
    }
    static IEnumerable<DependencyObject> Descendants(DependencyObject parent)
    {
        for(int i=0;i<VisualTreeHelper.GetChildrenCount(parent);i++)
        {
            var child=VisualTreeHelper.GetChild(parent,i);yield return child;
            foreach(var nested in Descendants(child)) yield return nested;
        }
    }
}
