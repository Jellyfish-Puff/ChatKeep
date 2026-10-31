using System.Windows;
using System.Windows.Controls;
namespace ChatArchive;
public sealed partial class ExportWindow : Window
{
    readonly int selectedCount;
    bool invalidStart,invalidEnd;
    public DateTime StartDate=>StartPicker.SelectedDate!.Value.Date;
    public DateTime EndDate=>EndPicker.SelectedDate!.Value.Date;
    public bool OnlySelected=>ContentPicker.SelectedIndex==1;
    public ExportWindow(int selected, DateTime? selectedStart=null, DateTime? selectedEnd=null,string chatName="",int loadedCount=0)
    {
        InitializeComponent();selectedCount=selected;
        MaxHeight=SystemParameters.WorkArea.Height;
        ChatName.Text=chatName;ChatName.ToolTip=chatName;
        if(chatName.Contains('\u20e3')) ChatName.FontFamily=new("Segoe UI Emoji, Microsoft YaHei UI");
        StartPicker.SelectedDate=selectedStart??DateTime.Today.AddDays(-7);
        EndPicker.SelectedDate=selectedEnd??DateTime.Today;
        SelectedContent.IsEnabled=selected>0;SelectedContent.Content=$"已勾选的消息（{selected} 条）";
        ContentPicker.SelectedIndex=selected>0?1:0;
        Summary.Text=$"当前已加载 {loadedCount} 条消息 · 已勾选 {selected} 条";
        StartPicker.DateValidationError+=(_,e)=>{e.ThrowException=false;StartPicker.SelectedDate=null;invalidStart=true;Error.Text="开始日期无效，请重新选择。";};
        EndPicker.DateValidationError+=(_,e)=>{e.ThrowException=false;EndPicker.SelectedDate=null;invalidEnd=true;Error.Text="结束日期无效，请重新选择。";};
        StartPicker.SelectedDateChanged+=(_,_)=>{invalidStart=false;Error.Text="";};
        EndPicker.SelectedDateChanged+=(_,_)=>{invalidEnd=false;Error.Text="";};
        UpdateHint();
    }
    void ContentChanged(object sender,SelectionChangedEventArgs e) {if(Hint!=null) UpdateHint();}
    void UpdateHint()=>Hint.Text=OnlySelected?"仅导出日期范围内已勾选的消息，包含搜索时隐藏的选择。":"导出日期范围内的全部本地记录，包含尚未加载的消息。";
    void ClearDates(object sender,RoutedEventArgs e) {StartPicker.SelectedDate=null;EndPicker.SelectedDate=null;StartPicker.Text="";EndPicker.Text="";invalidStart=invalidEnd=false;Error.Text="";}
    bool CanExport()
    {
        Error.Text=invalidStart || invalidEnd || StartPicker.SelectedDate==null || EndPicker.SelectedDate==null?"请选择有效的开始和结束日期。"
            :StartDate>EndDate?"开始日期不能晚于结束日期。"
            :EndDate==DateTime.MaxValue.Date?"请选择9999年12月31日之前的结束日期。"
            :OnlySelected && selectedCount==0?"请先勾选要导出的消息。":"";
        return Error.Text.Length==0;
    }
    void StartExport(object sender,RoutedEventArgs e) {if(CanExport()) DialogResult=true;}
}
