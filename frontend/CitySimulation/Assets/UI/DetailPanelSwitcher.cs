using UnityEngine;
using UnityEngine.UIElements;

/// <summary>
/// 使用 UI Toolkit 的“选项卡”切换：
/// 若干按钮控制右侧 detail 容器中不同 VisualElement 的显示。
/// 把本脚本挂在带有 UIDocument 的同一 GameObject 上即可。
/// </summary>
public class DetailPanelSwitcher : MonoBehaviour
{
    [Header("按钮 name（UXML 里 Button 的 name）")]
    public string[] buttonNames = { "edit", "running", "training", "evaluate", "playback" };

    [Header("detail 子元素 name（顺序与上面按钮一一对应）")]
    public string[] detailElementNames = { "edit", "running", "training", "evaluate", "playback" };

    private Button[] _buttons;
    private VisualElement[] _detailPanels;
    private VisualElement _detailRoot;

    private void Start()
    {
        var uiDocument = GetComponent<UIDocument>();
        if (uiDocument == null)
        {
            Debug.LogError("DetailPanelSwitcher: 未找到 UIDocument 组件。");
            return;
        }

        var root = uiDocument.rootVisualElement;
        _detailRoot = root.Q<VisualElement>("detail");
        if (_detailRoot == null)
        {
            Debug.LogError("DetailPanelSwitcher: 未找到名为 'detail' 的容器。");
            return;
        }

        int count = Mathf.Min(buttonNames.Length, detailElementNames.Length);
        _buttons = new Button[count];
        _detailPanels = new VisualElement[count];

        // 绑定按钮与面板
        for (int i = 0; i < count; i++)
        {
            if (!string.IsNullOrEmpty(buttonNames[i]))
            {
                _buttons[i] = root.Q<Button>(buttonNames[i]);
            }

            if (!string.IsNullOrEmpty(detailElementNames[i]))
            {
                _detailPanels[i] = _detailRoot.Q<VisualElement>(detailElementNames[i]);
            }
        }

        // 注册点击事件
        for (int i = 0; i < count; i++)
        {
            int index = i; // 捕获局部副本
            if (_buttons[i] != null)
            {
                _buttons[i].clicked += () => ShowPanel(index);
            }
        }

        // 默认显示第一个面板
        ShowPanel(0);
    }

    /// <summary>
    /// 显示指定索引的面板，其余面板隐藏。
    /// </summary>
    private void ShowPanel(int index)
    {
        if (_detailPanels == null || _detailPanels.Length == 0)
            return;

        for (int i = 0; i < _detailPanels.Length; i++)
        {
            var panel = _detailPanels[i];
            if (panel == null) continue;

            panel.style.display = (i == index) ? DisplayStyle.Flex : DisplayStyle.None;
        }
    }
}
