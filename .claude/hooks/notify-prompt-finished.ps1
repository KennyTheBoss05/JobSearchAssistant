[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime]

# Read hook context from stdin (Claude Code pipes JSON with session_id)
$sessionId = ''
try {
    $raw = [Console]::In.ReadToEnd()
    if ($raw -and $raw.Trim()) {
        $sessionId = ($raw | ConvertFrom-Json).session_id
    }
} catch {}

$launch = if ($sessionId) { "vscode://anthropic.claude-code/open?session=$sessionId" } else { 'vscode://anthropic.claude-code' }

$xmlString = @"
<toast activationType="protocol" launch="$launch">
  <visual>
    <binding template="ToastGeneric">
      <text>Claude Code</text>
      <text>Prompt finished — click to return</text>
    </binding>
  </visual>
</toast>
"@

$xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
$xml.LoadXml($xmlString)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Claude Code').Show($toast)
