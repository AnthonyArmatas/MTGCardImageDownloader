window.fileSystem = {
  pickDirectory: async () => {
    // This shows a folder picker; only works in secure contexts (HTTPS)
    const dirHandle = await window.showDirectoryPicker();
    const files = [];

    // Recursively iterate through entries:
    for await (const [name, entry] of dirHandle.entries()) {
      if (entry.kind === 'file') {
        const file = await entry.getFile();
        files.push({ name: file.name, size: file.size });
      }
    }
    return files;
  }
};
