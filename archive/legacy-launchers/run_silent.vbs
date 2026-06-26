Option Explicit

Dim fso, shell, repo, pyw, py, cmd, q
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
q = Chr(34)

repo = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = repo & "\venv\Scripts\pythonw.exe"
py = repo & "\venv\Scripts\python.exe"

If fso.FileExists(pyw) Then
    cmd = q & pyw & q & " " & q & repo & "\main.py" & q
ElseIf fso.FileExists(py) Then
    cmd = q & py & q & " " & q & repo & "\main.py" & q
Else
    cmd = "pythonw " & q & repo & "\main.py" & q
End If

shell.CurrentDirectory = repo
shell.Run cmd, 0, False