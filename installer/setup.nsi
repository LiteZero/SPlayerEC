Unicode true
!include "MUI2.nsh"
!include "x64.nsh"

Name "SPlayerEC"
OutFile "..\dist\SPlayerEC-1.0.1-x64-setup.exe"
InstallDir "$LOCALAPPDATA\Programs\SPlayerEC"
InstallDirRegKey HKCU "Software\SPlayerEC" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "SPlayerEC · K20 GT 歌词互联"
VIProductVersion "1.0.1.0"
VIAddVersionKey "ProductName" "SPlayerEC"
VIAddVersionKey "FileDescription" "SPlayerEC 安装程序"
VIAddVersionKey "FileVersion" "1.0.1"
VIAddVersionKey "LegalCopyright" "SPlayerEC contributors"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\SPlayerEC-Bridge.exe"
!define MUI_FINISHPAGE_RUN_TEXT "启动 SPlayerEC 桥接程序"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "此安装包需要 64 位 Windows"
    Abort
  ${EndIf}
FunctionEnd

Section "SPlayerEC"
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "..\dist\SPlayerEC-1.0.1-portable\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\SPlayerEC" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SPlayerEC" "DisplayName" "SPlayerEC · K20 GT 歌词互联"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SPlayerEC" "DisplayVersion" "1.0.1"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SPlayerEC" "DisplayIcon" "$INSTDIR\SPlayerEC-Bridge.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SPlayerEC" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SPlayerEC" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SPlayerEC" "NoRepair" 1
  CreateDirectory "$SMPROGRAMS\SPlayerEC"
  CreateShortcut "$SMPROGRAMS\SPlayerEC\K20 GT 歌词互联.lnk" "$INSTDIR\SPlayerEC-Bridge.exe"
  CreateShortcut "$SMPROGRAMS\SPlayerEC\歌词插件文件夹.lnk" "$INSTDIR\plugin"
  CreateShortcut "$SMPROGRAMS\SPlayerEC\使用说明.lnk" "$SYSDIR\notepad.exe" '$\"$INSTDIR\README.md$\"'
  CreateShortcut "$SMPROGRAMS\SPlayerEC\卸载.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  ExecWait '"$INSTDIR\SPlayerEC-Bridge.exe" --quit'
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "SPlayerEC"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SPlayerEC"
  DeleteRegKey HKCU "Software\SPlayerEC"
  Delete "$SMPROGRAMS\SPlayerEC\K20 GT 歌词互联.lnk"
  Delete "$SMPROGRAMS\SPlayerEC\歌词插件文件夹.lnk"
  Delete "$SMPROGRAMS\SPlayerEC\使用说明.lnk"
  Delete "$SMPROGRAMS\SPlayerEC\卸载.lnk"
  RMDir "$SMPROGRAMS\SPlayerEC"
  Delete "$INSTDIR\SPlayerEC-Bridge.exe"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\COPYING"
  Delete "$INSTDIR\COPYING.LESSER"
  Delete "$INSTDIR\THIRD_PARTY_NOTICES.md"
  Delete "$INSTDIR\VALIDATION.md"
  RMDir /r "$INSTDIR\licenses"
  Delete "$INSTDIR\SPlayerEC-1.0.0-source.zip"
  Delete "$INSTDIR\SPlayerEC-1.0.1-source.zip"
  Delete "$INSTDIR\plugin\k20gt-lyrics.js"
  RMDir "$INSTDIR\plugin"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
