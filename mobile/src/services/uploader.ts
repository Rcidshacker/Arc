import { Platform } from 'react-native';
import axios, { AxiosError } from 'axios';

export interface UploadProgress {
  loaded: number;
  total: number;
  percent: number;
}

interface UploadResponseData {
  meeting_id: string;
  sha256: string;
}

interface UploadApiResponse {
  data: UploadResponseData;
  error?: string;
}

interface ErrorApiResponse {
  error: string;
}

// expo-file-system is native-only — conditionally required
let FileSystem: { getInfoAsync(uri: string): Promise<{ exists: boolean; size?: number }> } | null = null;
if (Platform.OS !== 'web') {
  FileSystem = require('expo-file-system');
}

export async function uploadAudio(
  fileUri: string,
  serverUrl: string,
  onProgress: (progress: UploadProgress) => void,
): Promise<{ meetingId: string; sha256: string }> {
  if (Platform.OS === 'web') {
    return uploadAudioWeb(fileUri, serverUrl, onProgress);
  }
  return uploadAudioNative(fileUri, serverUrl, onProgress);
}

// ---------------------------------------------------------------------------
// Web upload — fileUri is a blob: URL from MediaRecorder
// ---------------------------------------------------------------------------

async function uploadAudioWeb(
  fileUri: string,
  serverUrl: string,
  onProgress: (progress: UploadProgress) => void,
): Promise<{ meetingId: string; sha256: string }> {
  // Fetch the blob from the object URL created during stopRecording()
  const blobResponse = await fetch(fileUri);
  const blob = await blobResponse.blob();

  const formData = new FormData();
  // Server accepts any audio — webm works with ffmpeg normalizer
  formData.append('file', blob, 'recording.webm');

  return new Promise<{ meetingId: string; sha256: string }>((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.onprogress = (e: ProgressEvent) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        onProgress({ loaded: e.loaded, total: e.total, percent });
      }
    };

    xhr.onload = () => {
      if (xhr.status === 409) {
        reject(new Error('This recording was already uploaded.'));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const resp: UploadApiResponse = JSON.parse(xhr.responseText);
          const { meeting_id, sha256 } = resp.data;
          resolve({ meetingId: meeting_id, sha256 });
        } catch {
          reject(new Error('Invalid server response.'));
        }
        return;
      }
      try {
        const resp: ErrorApiResponse = JSON.parse(xhr.responseText);
        reject(new Error(resp.error ?? `Upload failed with status ${xhr.status}.`));
      } catch {
        reject(new Error(`Upload failed with status ${xhr.status}.`));
      }
    };

    xhr.onerror = () =>
      reject(new Error('Cannot reach the server. Make sure the laptop is on the same network.'));
    xhr.ontimeout = () =>
      reject(new Error('Upload timed out. Check your network and try again.'));

    xhr.timeout = 300_000;
    xhr.open('POST', `${serverUrl}/upload`);
    xhr.send(formData);
  });
}

// ---------------------------------------------------------------------------
// Native upload — fileUri is a file:// URI from expo-audio
// ---------------------------------------------------------------------------

async function uploadAudioNative(
  fileUri: string,
  serverUrl: string,
  onProgress: (progress: UploadProgress) => void,
): Promise<{ meetingId: string; sha256: string }> {
  const fileInfo = await FileSystem!.getInfoAsync(fileUri);

  if (!fileInfo.exists) {
    throw new Error('Audio file not found at the specified path.');
  }

  const filename = fileUri.split('/').pop() ?? 'recording.m4a';
  const mimeType = filename.endsWith('.m4a') ? 'audio/mp4' : 'audio/mpeg';

  const formData = new FormData();
  formData.append('file', {
    uri: fileUri,
    name: filename,
    type: mimeType,
  } as unknown as Blob);

  try {
    const response = await axios.post<UploadApiResponse>(
      `${serverUrl}/upload`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent) => {
          const total = progressEvent.total ?? fileInfo.size ?? 1;
          const loaded = progressEvent.loaded;
          const percent = Math.round((loaded / total) * 100);
          onProgress({ loaded, total, percent });
        },
        timeout: 300_000,
      },
    );

    const { meeting_id, sha256 } = response.data.data;
    return { meetingId: meeting_id, sha256 };
  } catch (err) {
    const axiosError = err as AxiosError<ErrorApiResponse>;

    if (axiosError.response?.status === 409) {
      throw new Error('This recording was already uploaded.');
    }

    const serverMessage = axiosError.response?.data?.error;
    if (serverMessage) {
      throw new Error(serverMessage);
    }

    if (axiosError.code === 'ECONNABORTED') {
      throw new Error('Upload timed out. Check your network and try again.');
    }

    if (axiosError.code === 'ECONNREFUSED' || !axiosError.response) {
      throw new Error('Cannot reach the server. Make sure the laptop is on the same network.');
    }

    throw new Error('Upload failed. Please try again.');
  }
}
