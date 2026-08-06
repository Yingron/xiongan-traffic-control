using UnityEngine;
using UnityEngine.UIElements;

public class SidebarController : MonoBehaviour
{
    public Button collapseButton;       // 按钮
    public VisualElement controlPanel;  // 控制面板

    void Start()
    {
        // 获取 UIDocument 的 root VisualElement
        var root = GetComponent<UIDocument>().rootVisualElement;

        // 查找按钮和控制面板
        collapseButton = root.Q<Button>("collapseButton");   // 按钮名称为 "collapseButton"
        controlPanel = root.Q<VisualElement>("controlPanel"); // 控制面板名称为 "controlPanel"

        // 绑定按钮点击事件
        collapseButton.clicked += ToggleControlPanelVisibility;
    }

    // 按钮点击时调用的方法
    void ToggleControlPanelVisibility()
    {
        if (controlPanel.style.display == DisplayStyle.None)
        {
            controlPanel.style.display = DisplayStyle.Flex;  // 显示控制面板
            collapseButton.text = "fold";  // 更改按钮文本为 "fold"
        }
        else
        {
            controlPanel.style.display = DisplayStyle.None;  // 隐藏控制面板
            collapseButton.text = "unfold";  // 更改按钮文本为 "unfold"
        }
    }
}
