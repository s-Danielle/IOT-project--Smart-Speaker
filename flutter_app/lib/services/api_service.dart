import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import '../models/status.dart';
import '../models/chip.dart';
import '../models/song.dart';

/// An answer from the speaker that was not a success.
///
/// [toString] is a sentence that can be shown to the user as it is.
class ApiException implements Exception {
  final int statusCode;
  final String message;

  ApiException(this.statusCode, this.message);

  @override
  String toString() => message;
}

class ApiService {
  final String baseUrl;

  ApiService(this.baseUrl);

  // ===========================================================================
  // THE ONE PLACE THAT TALKS HTTP
  // Every request goes through these helpers.
  // ===========================================================================

  Map<String, String> _headers({bool json = false}) {
    return json ? {'Content-Type': 'application/json'} : {};
  }

  Future<http.Response> _get(String path) async {
    return http.get(Uri.parse('$baseUrl$path'), headers: _headers());
  }

  Future<http.Response> _post(String path, [Map<String, dynamic>? body]) async {
    return http.post(
      Uri.parse('$baseUrl$path'),
      headers: _headers(json: body != null),
      body: body == null ? null : jsonEncode(body),
    );
  }

  Future<http.Response> _put(String path, Map<String, dynamic> body) async {
    return http.put(
      Uri.parse('$baseUrl$path'),
      headers: _headers(json: true),
      body: jsonEncode(body),
    );
  }

  Future<http.Response> _delete(String path) async {
    return http.delete(Uri.parse('$baseUrl$path'), headers: _headers());
  }

  /// The error to throw for an answer that was not a success.
  ApiException _failure(String what, http.Response response) {
    var detail = '';
    try {
      final body = jsonDecode(response.body);
      if (body is Map && body['error'] is String) {
        detail = ': ${body['error']}';
      }
    } on FormatException {
      // the answer was not JSON: say only the number
    }
    return ApiException(
      response.statusCode,
      'Failed to $what (${response.statusCode})$detail',
    );
  }

  /// The JSON object in a 200 answer, or an [ApiException].
  Map<String, dynamic> _object(String what, http.Response response) {
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw _failure(what, response);
  }

  // GET /status
  Future<Status> getStatus() async {
    final response = await _get('/status');
    return Status.fromJson(_object('get status', response));
  }

  // GET /chips
  Future<List<SpeakerChip>> getChips() async {
    final response = await _get('/chips');
    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((json) => SpeakerChip.fromJson(json)).toList();
    }
    throw _failure('get chips', response);
  }

  // POST /chips - Register a new chip
  Future<SpeakerChip> createChip(String uid, {String? name}) async {
    final response = await _post('/chips', {'uid': uid, 'name': name ?? ''});
    if (response.statusCode == 200 || response.statusCode == 201) {
      return SpeakerChip.fromJson(jsonDecode(response.body));
    }
    throw _failure('create chip', response);
  }

  // PUT /chips/{chip_id}
  Future<void> updateChip(String chipId, {String? name, String? songId}) async {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (songId != null) body['song_id'] = songId;

    final response = await _put('/chips/$chipId', body);
    if (response.statusCode != 200) {
      throw _failure('update chip', response);
    }
  }

  // DELETE /chips/{chip_id}/assignment
  Future<void> resetChipAssignment(String chipId) async {
    final response = await _delete('/chips/$chipId/assignment');
    if (response.statusCode != 200 && response.statusCode != 204) {
      throw _failure('reset assignment', response);
    }
  }

  // DELETE /chips/{chip_id}
  Future<void> deleteChip(String chipId) async {
    final response = await _delete('/chips/$chipId');
    if (response.statusCode != 200 && response.statusCode != 204) {
      throw _failure('delete chip', response);
    }
  }

  // GET /library
  Future<List<Song>> getLibrary() async {
    final response = await _get('/library');
    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((json) => Song.fromJson(json)).toList();
    }
    throw _failure('get library', response);
  }

  // POST /library
  Future<Song> createSong(String name, String uri) async {
    final response = await _post('/library', {'name': name, 'uri': uri});
    if (response.statusCode == 200 || response.statusCode == 201) {
      return Song.fromJson(jsonDecode(response.body));
    }
    throw _failure('create song', response);
  }

  // PUT /library/{song_id}
  Future<void> updateSong(String songId, String name, String uri) async {
    final response = await _put('/library/$songId', {'name': name, 'uri': uri});
    if (response.statusCode != 200) {
      throw _failure('update song', response);
    }
  }

  // DELETE /library/{song_id}
  Future<void> deleteSong(String songId) async {
    final response = await _delete('/library/$songId');
    if (response.statusCode != 200 && response.statusCode != 204) {
      throw _failure('delete song', response);
    }
  }

  // POST /files (multipart/form-data)
  // Takes raw bytes so it works on both native and web builds.
  //
  // The speaker adds the uploaded file to the library by itself, and answers
  // with that entry (its id is '' on an older speaker). The caller must NOT also create a library entry for it
  // (that made two entries for one file); to give it another name, rename
  // the returned entry with [updateSong].
  Future<Song> uploadFileBytes(Uint8List bytes, String filename) async {
    final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/files'));
    request.headers.addAll(await _headers());
    request.files.add(
      http.MultipartFile.fromBytes('file', bytes, filename: filename),
    );

    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200 || response.statusCode == 201) {
      // An older speaker does not send the entry's id. Then the id is '' and the
      // caller finds the entry by its link instead.
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return Song(
        id: (data['id'] ?? '').toString(),
        name: (data['name'] ?? '').toString(),
        uri: (data['uri'] ?? '').toString(),
      );
    }
    throw _failure('upload file', response);
  }

  // ===========================================================================
  // PARENTAL CONTROLS
  // ===========================================================================

  // GET /settings/parental
  Future<Map<String, dynamic>> getParentalSettings() async {
    final response = await _get('/settings/parental');
    return _object('get parental settings', response);
  }

  // PUT /settings/parental
  Future<Map<String, dynamic>> updateParentalSettings(
      Map<String, dynamic> settings) async {
    final response = await _put('/settings/parental', settings);
    return _object('update parental settings', response);
  }

  // ===========================================================================
  // DEBUG / DEVELOPER TOOLS
  // ===========================================================================

  // GET /debug/i2c
  Future<Map<String, dynamic>> getI2cDevices() async {
    return _object('get I2C devices', await _get('/debug/i2c'));
  }

  // GET /debug/system
  Future<Map<String, dynamic>> getSystemInfo() async {
    return _object('get system info', await _get('/debug/system'));
  }

  // GET /debug/logs
  Future<Map<String, dynamic>> getLogs() async {
    return _object('get logs', await _get('/debug/logs'));
  }

  // GET /debug/git-status
  Future<Map<String, dynamic>> getGitStatus() async {
    return _object('get git status', await _get('/debug/git-status'));
  }

  // POST /debug/git-pull
  Future<Map<String, dynamic>> gitPull() async {
    return _object('git pull', await _post('/debug/git-pull'));
  }

  // GET /debug/speaker/status
  Future<Map<String, dynamic>> getSpeakerStatus() async {
    return _object('get speaker status', await _get('/debug/speaker/status'));
  }

  // POST /debug/speaker/start
  Future<Map<String, dynamic>> startSpeaker() async {
    return _object('start speaker', await _post('/debug/speaker/start'));
  }

  // POST /debug/speaker/stop
  Future<Map<String, dynamic>> stopSpeaker() async {
    return _object('stop speaker', await _post('/debug/speaker/stop'));
  }

  // POST /debug/speaker/restart
  Future<Map<String, dynamic>> restartSpeaker() async {
    return _object('restart speaker', await _post('/debug/speaker/restart'));
  }

  // POST /debug/daemon-reload
  Future<Map<String, dynamic>> daemonReload() async {
    return _object('daemon reload', await _post('/debug/daemon-reload'));
  }

  // POST /debug/reboot
  Future<Map<String, dynamic>> rebootPi() async {
    return _object('reboot', await _post('/debug/reboot'));
  }

  // ===========================================================================
  // WIFI MANAGEMENT
  // ===========================================================================

  // GET /debug/wifi/status
  Future<Map<String, dynamic>> getWifiStatus() async {
    return _object('get WiFi status', await _get('/debug/wifi/status'));
  }

  // GET /debug/wifi/connections
  Future<Map<String, dynamic>> getWifiConnections() async {
    return _object('get WiFi connections', await _get('/debug/wifi/connections'));
  }

  // GET /debug/wifi/scan
  Future<Map<String, dynamic>> scanWifiNetworks() async {
    return _object('scan WiFi networks', await _get('/debug/wifi/scan'));
  }

  // POST /debug/wifi/connect
  Future<Map<String, dynamic>> connectWifi(String ssid, {String? password}) async {
    final response =
        await _post('/debug/wifi/connect', {'ssid': ssid, 'password': password});
    return _object('connect to WiFi', response);
  }

  // POST /debug/wifi/disconnect
  Future<Map<String, dynamic>> disconnectWifi() async {
    return _object('disconnect WiFi', await _post('/debug/wifi/disconnect'));
  }

  // POST /debug/wifi/forget
  Future<Map<String, dynamic>> forgetWifi(String name) async {
    final response = await _post('/debug/wifi/forget', {'name': name});
    return _object('forget WiFi', response);
  }

  // POST /debug/wifi/priority
  Future<Map<String, dynamic>> setWifiPriority(String name, int priority) async {
    final response =
        await _post('/debug/wifi/priority', {'name': name, 'priority': priority});
    return _object('set WiFi priority', response);
  }

  // GET /debug/wifi/connect-status — poll after POST /debug/wifi/connect
  // state: "idle" | "connecting" | "connected" | "failed"
  Future<Map<String, dynamic>> getWifiConnectStatus() async {
    final response =
        await _get('/debug/wifi/connect-status').timeout(const Duration(seconds: 5));
    return _object('get connect status', response);
  }

  // Probe whether the server is reachable (short timeout).
  Future<bool> isReachable({int timeoutSeconds = 3}) async {
    try {
      final response =
          await _get('/status').timeout(Duration(seconds: timeoutSeconds));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // POST /debug/wifi/ap-mode
  Future<Map<String, dynamic>> setApMode(bool enable) async {
    final response = await _post('/debug/wifi/ap-mode', {'enable': enable});
    return _object('set AP mode', response);
  }
}
