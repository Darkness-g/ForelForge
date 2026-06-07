const { app, BrowserWindow, dialog, ipcMain, net } = require('electron');
const path = require('path');
const fs = require('fs');

let mainWindow;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 900,
        height: 600,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js')
        }
    });

    mainWindow.loadFile('index.html');
}

ipcMain.handle('download-game', async (event, { url, filename }) => {
    const { canceled, filePath } = await dialog.showSaveDialog({
        title: 'Куда сохранить игру',
        defaultPath: filename
    });

    if (canceled) return { success: false };

    return new Promise((resolve, reject) => {
        const request = net.request(url);
        const file = fs.createWriteStream(filePath);

        request.on('response', (response) => {

    const totalHeader = response.headers['content-length'];
    const total = totalHeader ? parseInt(totalHeader[0], 10) : null;

    let downloaded = 0;

    response.on('data', (chunk) => {
        downloaded += chunk.length;

        if (total) {
            const percent = Math.round((downloaded / total) * 100);
            mainWindow.webContents.send('download-progress', percent);
        }
    });

    response.pipe(file);

    response.on('end', () => {
        mainWindow.webContents.send('download-progress', 100);
        resolve({ success: true });
    });
});


        request.on('error', (error) => {
            fs.unlink(filePath, () => {});
            reject(error);
        });

        request.end();
    });
});

app.whenReady().then(createWindow);
