import * as vscode from 'vscode';
import * as http from 'http';

let server: http.Server | null = null;

export function activate(context: vscode.ExtensionContext) {
  const port = 48100;
  server = http.createServer(async (req, res) => {
    try {
      if (!req.url) { res.writeHead(400); return res.end('No URL'); }
      if (req.method === 'POST' && req.url === '/saveAll') {
        await vscode.workspace.saveAll();
        res.writeHead(200, { 'Content-Type': 'text/plain' });
        return res.end('ok');
      }
      if (req.method === 'GET' && req.url === '/diagnostics') {
        const diags = vscode.languages.getDiagnostics();
        const out = diags.map(([uri, d]) => ({
          uri: uri.toString(),
          diagnostics: d.map(x => ({
            message: x.message,
            severity: x.severity,
            range: {
              start: { line: x.range.start.line, character: x.range.start.character },
              end: { line: x.range.end.line, character: x.range.end.character }
            },
            source: x.source
          }))
        }));
        res.writeHead(200, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify(out));
      }
      res.writeHead(404);
      res.end('Not found');
    } catch (e:any) {
      res.writeHead(500);
      res.end(String(e?.message || e));
    }
  });
  server.listen(port, '127.0.0.1', () => {
    console.log('Desktop Operator bridge on http://127.0.0.1:' + port);
  });

  context.subscriptions.push(vscode.commands.registerCommand('desktopOperator.saveAll', async () => {
    await vscode.workspace.saveAll();
    vscode.window.showInformationMessage('Saved all files.');
  }));

  context.subscriptions.push(new vscode.Disposable(() => {
    if (server) server.close();
  }));
}

export function deactivate() {
  if (server) server.close();
}
