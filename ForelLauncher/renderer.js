window.launcher.onProgress((percent) => {
    const bar = document.getElementById('progressBar');
    const text = document.getElementById('progressText');

    if (bar && text) {
        bar.style.width = percent + "%";
        text.innerText = percent + "%";
    }
});

async function download() {
    const game = {
        url: "https://itorrents-igruha.org/?do=download&id=98935",
        filename: ""
    };

    await window.launcher.downloadGame(game);
}

