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
}

