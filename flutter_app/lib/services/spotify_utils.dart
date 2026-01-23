/// Converts a Spotify URL to a Spotify URI.
/// 
/// Examples:
/// - https://open.spotify.com/track/ABC123?si=xyz → spotify:track:ABC123
/// - https://open.spotify.com/playlist/XYZ → spotify:playlist:XYZ
/// - https://open.spotify.com/album/123 → spotify:album:123
/// 
/// Returns the original input if it's already a URI or not a valid Spotify URL.
String convertSpotifyUrlToUri(String input) {
  final trimmed = input.trim();
  
  // Already a Spotify URI
  if (trimmed.startsWith('spotify:')) {
    return trimmed;
  }
  
  // Not a Spotify URL
  if (!trimmed.startsWith('https://open.spotify.com/') && 
      !trimmed.startsWith('http://open.spotify.com/')) {
    return trimmed;
  }
  
  try {
    final uri = Uri.parse(trimmed);
    final pathSegments = uri.pathSegments;
    
    // Need at least 2 segments: type and id
    if (pathSegments.length < 2) {
      return trimmed;
    }
    
    final type = pathSegments[0]; // track, playlist, album, artist, etc.
    final id = pathSegments[1];   // the Spotify ID
    
    // Validate type
    const validTypes = ['track', 'playlist', 'album', 'artist', 'episode', 'show'];
    if (!validTypes.contains(type)) {
      return trimmed;
    }
    
    return 'spotify:$type:$id';
  } catch (e) {
    return trimmed;
  }
}

/// Checks if the input looks like a Spotify URL that can be converted.
bool isSpotifyUrl(String input) {
  final trimmed = input.trim();
  return trimmed.startsWith('https://open.spotify.com/') || 
         trimmed.startsWith('http://open.spotify.com/');
}

/// Checks if the input is a Spotify URI.
bool isSpotifyUri(String input) {
  return input.trim().startsWith('spotify:');
}

