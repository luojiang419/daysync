const SUPPORTED_MEDIA_EXTENSIONS = [".mov", ".mp4", ".wav", ".m4a"];

export function normalizeDroppedDirectories(paths: string[]): string[] {
  const unique = new Set<string>();

  paths.forEach((rawPath) => {
    const path = rawPath.trim();
    if (!path) {
      return;
    }
    const normalized = coercePathToDirectory(path);
    if (normalized) {
      unique.add(normalized);
    }
  });

  return Array.from(unique);
}

export function assignDroppedDirectories(
  currentVideoDirectory: string,
  currentAudioDirectory: string,
  droppedPaths: string[],
): {
  videoDirectory: string;
  audioDirectory: string;
  acceptedCount: number;
  ignoredCount: number;
} {
  const directories = normalizeDroppedDirectories(droppedPaths);
  let videoDirectory = currentVideoDirectory;
  let audioDirectory = currentAudioDirectory;
  let acceptedCount = 0;
  let cursor = 0;

  if (!videoDirectory && directories[cursor]) {
    videoDirectory = directories[cursor];
    cursor += 1;
    acceptedCount += 1;
  }

  if (!audioDirectory && directories[cursor]) {
    audioDirectory = directories[cursor];
    cursor += 1;
    acceptedCount += 1;
  }

  return {
    videoDirectory,
    audioDirectory,
    acceptedCount,
    ignoredCount: directories.length - acceptedCount,
  };
}

function coercePathToDirectory(path: string): string {
  const lowerPath = path.toLowerCase();
  const matchedExtension = SUPPORTED_MEDIA_EXTENSIONS.find((extension) => lowerPath.endsWith(extension));
  if (!matchedExtension) {
    return path;
  }

  const lastSlash = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
  if (lastSlash <= 0) {
    return path;
  }
  return path.slice(0, lastSlash);
}
