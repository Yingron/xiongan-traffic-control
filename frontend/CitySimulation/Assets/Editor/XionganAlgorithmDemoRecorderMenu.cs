using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class XionganAlgorithmDemoRecorderMenu
{
    const string OutputKey = "Xiongan.AlgorithmDemo.Output";
    const string FfmpegKey = "Xiongan.AlgorithmDemo.Ffmpeg";
    const string ScenePath = "Assets/Scenes/City.unity";

    public static void Run()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode || EditorApplication.isCompiling || EditorApplication.isUpdating)
            throw new InvalidOperationException("Unity当前不适合开始录制。");
        if (EditorSceneManager.GetActiveScene().isDirty)
            throw new InvalidOperationException("当前场景有未保存修改，录制已停止以避免覆盖。");

        var output = GetArgument("-recordOutput");
        var ffmpeg = GetArgument("-ffmpegPath");
        if (string.IsNullOrWhiteSpace(output) || string.IsNullOrWhiteSpace(ffmpeg))
            throw new ArgumentException("缺少-recordOutput或-ffmpegPath参数。");

        Directory.CreateDirectory(Path.GetDirectoryName(output));
        EditorPrefs.SetString(OutputKey, output);
        EditorPrefs.SetString(FfmpegKey, ffmpeg);
        EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
        EditorApplication.isPlaying = true;
        Debug.Log("[AlgorithmDemoRecorder] 175秒算法闭环演示录制已启动：" + output);
    }

    static string GetArgument(string name)
    {
        var args = Environment.GetCommandLineArgs();
        for (var index = 0; index < args.Length - 1; index++)
            if (string.Equals(args[index], name, StringComparison.OrdinalIgnoreCase)) return args[index + 1];
        return null;
    }
}
