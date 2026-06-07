const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('launcher', {
    downloadGame: (data) => ipcRenderer.invoke('download-game', data),
    onProgress: (callback) => ipcRenderer.on('download-progress', (_, percent) => callback(percent))
});

