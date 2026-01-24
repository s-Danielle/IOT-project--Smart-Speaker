import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/status.dart';
import '../models/chip.dart';
import '../models/song.dart';

class ApiService {
  final String baseUrl;

  ApiService(this.baseUrl);

  // GET /status
  Future<Status> getStatus() async {
    final response = await http.get(Uri.parse('$baseUrl/status'));
    if (response.statusCode == 200) {
      return Status.fromJson(jsonDecode(response.body));
    }
    throw Exception('Failed to get status: ${response.statusCode}');
  }

  // GET /chips
  Future<List<SpeakerChip>> getChips() async {
    final response = await http.get(Uri.parse('$baseUrl/chips'));
    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((json) => SpeakerChip.fromJson(json)).toList();
    }
    throw Exception('Failed to get chips: ${response.statusCode}');
  }

  // POST /chips - Register a new chip
  Future<SpeakerChip> createChip(String uid, {String? name}) async {
    final response = await http.post(
      Uri.parse('$baseUrl/chips'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'uid': uid, 'name': name ?? ''}),
    );
    if (response.statusCode == 200 || response.statusCode == 201) {
      return SpeakerChip.fromJson(jsonDecode(response.body));
    }
    throw Exception('Failed to create chip: ${response.statusCode}');
  }

  // PUT /chips/{chip_id}
  Future<void> updateChip(String chipId, {String? name, String? songId}) async {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (songId != null) body['song_id'] = songId;

    final response = await http.put(
      Uri.parse('$baseUrl/chips/$chipId'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to update chip: ${response.statusCode}');
    }
  }

  // DELETE /chips/{chip_id}/assignment
  Future<void> resetChipAssignment(String chipId) async {
    final response = await http.delete(
      Uri.parse('$baseUrl/chips/$chipId/assignment'),
    );
    if (response.statusCode != 200 && response.statusCode != 204) {
      throw Exception('Failed to reset assignment: ${response.statusCode}');
    }
  }

  // DELETE /chips/{chip_id}
  Future<void> deleteChip(String chipId) async {
    final response = await http.delete(
      Uri.parse('$baseUrl/chips/$chipId'),
    );
    if (response.statusCode != 200 && response.statusCode != 204) {
      throw Exception('Failed to delete chip: ${response.statusCode}');
    }
  }

  // GET /library
  Future<List<Song>> getLibrary() async {
    final response = await http.get(Uri.parse('$baseUrl/library'));
    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((json) => Song.fromJson(json)).toList();
    }
    throw Exception('Failed to get library: ${response.statusCode}');
  }

  // POST /library
  Future<Song> createSong(String name, String uri) async {
    final response = await http.post(
      Uri.parse('$baseUrl/library'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name, 'uri': uri}),
    );
    if (response.statusCode == 200 || response.statusCode == 201) {
      return Song.fromJson(jsonDecode(response.body));
    }
    throw Exception('Failed to create song: ${response.statusCode}');
  }

  // PUT /library/{song_id}
  Future<void> updateSong(String songId, String name, String uri) async {
    final response = await http.put(
      Uri.parse('$baseUrl/library/$songId'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name, 'uri': uri}),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to update song: ${response.statusCode}');
    }
  }

  // DELETE /library/{song_id}
  Future<void> deleteSong(String songId) async {
    final response = await http.delete(
      Uri.parse('$baseUrl/library/$songId'),
    );
    if (response.statusCode != 200 && response.statusCode != 204) {
      throw Exception('Failed to delete song: ${response.statusCode}');
    }
  }

  // POST /files (multipart/form-data)
  Future<String> uploadFile(File file) async {
    final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/files'));
    request.files.add(await http.MultipartFile.fromPath('file', file.path));
    
    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);
    
    if (response.statusCode == 200 || response.statusCode == 201) {
      final data = jsonDecode(response.body);
      return data['uri'];
    }
    throw Exception('Failed to upload file: ${response.statusCode}');
  }

  // ===========================================================================
  // PARENTAL CONTROLS
  // ===========================================================================

  // GET /settings/parental
  Future<Map<String, dynamic>> getParentalSettings() async {
    final response = await http.get(Uri.parse('$baseUrl/settings/parental'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to get parental settings: ${response.statusCode}');
  }

  // PUT /settings/parental
  Future<Map<String, dynamic>> updateParentalSettings(Map<String, dynamic> settings) async {
    final response = await http.put(
      Uri.parse('$baseUrl/settings/parental'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(settings),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to update parental settings: ${response.statusCode}');
  }

  // ===========================================================================
  // DEBUG / DEVELOPER TOOLS
  // ===========================================================================

  // GET /debug/i2c
  Future<Map<String, dynamic>> getI2cDevices() async {
    final response = await http.get(Uri.parse('$baseUrl/debug/i2c'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to get I2C devices: ${response.statusCode}');
  }

  // GET /debug/system
  Future<Map<String, dynamic>> getSystemInfo() async {
    final response = await http.get(Uri.parse('$baseUrl/debug/system'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to get system info: ${response.statusCode}');
  }

  // GET /debug/logs
  Future<Map<String, dynamic>> getLogs() async {
    final response = await http.get(Uri.parse('$baseUrl/debug/logs'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to get logs: ${response.statusCode}');
  }

  // GET /debug/git-status
  Future<Map<String, dynamic>> getGitStatus() async {
    final response = await http.get(Uri.parse('$baseUrl/debug/git-status'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to get git status: ${response.statusCode}');
  }

  // POST /debug/git-pull
  Future<Map<String, dynamic>> gitPull() async {
    final response = await http.post(Uri.parse('$baseUrl/debug/git-pull'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to git pull: ${response.statusCode}');
  }

  // GET /debug/speaker/status
  Future<Map<String, dynamic>> getSpeakerStatus() async {
    final response = await http.get(Uri.parse('$baseUrl/debug/speaker/status'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to get speaker status: ${response.statusCode}');
  }

  // POST /debug/speaker/start
  Future<Map<String, dynamic>> startSpeaker() async {
    final response = await http.post(Uri.parse('$baseUrl/debug/speaker/start'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to start speaker: ${response.statusCode}');
  }

  // POST /debug/speaker/stop
  Future<Map<String, dynamic>> stopSpeaker() async {
    final response = await http.post(Uri.parse('$baseUrl/debug/speaker/stop'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to stop speaker: ${response.statusCode}');
  }

  // POST /debug/speaker/restart
  Future<Map<String, dynamic>> restartSpeaker() async {
    final response = await http.post(Uri.parse('$baseUrl/debug/speaker/restart'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to restart speaker: ${response.statusCode}');
  }

  // POST /debug/daemon-reload
  Future<Map<String, dynamic>> daemonReload() async {
    final response = await http.post(Uri.parse('$baseUrl/debug/daemon-reload'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to daemon reload: ${response.statusCode}');
  }

  // POST /debug/run-main
  Future<Map<String, dynamic>> runMain() async {
    final response = await http.post(Uri.parse('$baseUrl/debug/run-main'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to run main: ${response.statusCode}');
  }

  // POST /debug/reboot
  Future<Map<String, dynamic>> rebootPi() async {
    final response = await http.post(Uri.parse('$baseUrl/debug/reboot'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to reboot: ${response.statusCode}');
  }
}

