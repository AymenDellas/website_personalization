const cp = require('child_process');

console.log("Fetching process list...");
cp.exec('tasklist /v /fo csv', { maxBuffer: 10 * 1024 * 1024 }, (err, stdout) => {
    if (err) {
        console.error("Error running tasklist:", err);
        return;
    }
    
    const lines = stdout.split('\n');
    let killed = 0;
    
    lines.forEach(line => {
        const lowerLine = line.toLowerCase();
        // Look for chrome.exe processes that have "Testing" in their window title or image name
        if (lowerLine.includes('chrome.exe') && lowerLine.includes('testing')) {
            // Tasklist CSV format: "Image Name","PID","Session Name","Session#","Mem Usage","Status","User Name","CPU Time","Window Title"
            const parts = line.split('","');
            if (parts.length >= 2) {
                const pid = parts[1].replace('"', '');
                if (pid && !isNaN(pid)) {
                    console.log('Killing PID ' + pid);
                    try {
                        cp.execSync('taskkill /f /pid ' + pid, { stdio: 'ignore' });
                        killed++;
                    } catch (e) {
                        console.log('Failed to kill PID ' + pid);
                    }
                }
            }
        }
    });
    
    console.log('Successfully killed ' + killed + ' Google Chrome for Testing processes.');
});
