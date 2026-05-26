import * as FileSystem from 'expo-file-system';
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

export async function uploadAudio(
  fileUri: string,
  serverUrl: string,
  onProgress: (progress: UploadProgress) => void,
): Promise<{ meetingId: string; sha256: string }> {
  const fileInfo = await FileSystem.getInfoAsync(fileUri);

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
        timeout: 300_000, // 5 minutes
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
