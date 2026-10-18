using System.Windows;
using System.Windows.Controls;
namespace ChatArchive;
public sealed class ExportWindow : Window
{
    readonly DatePicker start=new(){SelectedDate=DateTime.Today.AddDays(-7)};
    readonly DatePicker end=new(){SelectedDate=DateTime.Today};
    readonly CheckBox only=new(){Content="仅导出我已勾选的消息",Margin=new Thickness(0,20,0,16)};
    public DateTime StartDate=>start.SelectedDate!.Value;
    public DateTime EndDate=>end.SelectedDate!.Value;
    public bool OnlySelected=>only.IsChecked==true;
    public ExportWindow(int selected, DateTime? selectedStart=null, DateTime? selectedEnd=null)
    {
        Title="导出聊天记录";Width=460;Height=510;ResizeMode=ResizeMode.NoResize;WindowStartupLocation=WindowStartupLocation.CenterOwner;FontFamily=new("Microsoft YaHei UI");FontSize=14;
        var panel=new StackPanel{Margin=new Thickness(28)};Content=panel;
        panel.Children.Add(new TextBlock{Text="选择导出范围",FontSize=22,FontWeight=FontWeights.SemiBold,Margin=new Thickness(0,0,0,20)});
        panel.Children.Add(new TextBlock{Text="开始日期",Margin=new Thickness(0,0,0,6)});panel.Children.Add(start);
        panel.Children.Add(new TextBlock{Text="结束日期（包含当天）",Margin=new Thickness(0,14,0,6)});panel.Children.Add(end);
        only.IsEnabled=selected>0;only.IsChecked=selected>0;panel.Children.Add(only);
        if(selectedStart!=null) start.SelectedDate=selectedStart;
        if(selectedEnd!=null) end.SelectedDate=selectedEnd;
        panel.Children.Add(new TextBlock{Text="导出格式",Margin=new Thickness(0,0,0,6)});
        var format=new ComboBox{SelectedIndex=0,Padding=new Thickness(8)};format.Items.Add("HTML · 文字与图片保存在一个文件");panel.Children.Add(format);
        var buttons=new StackPanel{Orientation=Orientation.Horizontal,HorizontalAlignment=HorizontalAlignment.Right,Margin=new Thickness(0,22,0,0)};
        var cancel=new Button{Content="取消",IsCancel=true};var export=new Button{Content="确认导出",IsDefault=true};buttons.Children.Add(cancel);buttons.Children.Add(export);panel.Children.Add(buttons);
        export.Click+=(_,_)=>{if(start.SelectedDate==null||end.SelectedDate==null||StartDate>EndDate){MessageBox.Show(this,"请选择有效的日期范围。",Title);return;}DialogResult=true;};
    }
}
