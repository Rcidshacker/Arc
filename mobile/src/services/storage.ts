import AsyncStorage from '@react-native-async-storage/async-storage';

const SERVER_URL_KEY = 'arc_server_url';
const USER_NAME_KEY = 'arc_user_name';
const DEVICE_ID_KEY = 'arc_device_id';
const NAME_PROMPTED_KEY = 'arc_name_prompted';

function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export async function getServerUrl(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(SERVER_URL_KEY);
  } catch {
    return null;
  }
}

export async function setServerUrl(url: string): Promise<void> {
  await AsyncStorage.setItem(SERVER_URL_KEY, url);
}

export async function clearServerUrl(): Promise<void> {
  await AsyncStorage.removeItem(SERVER_URL_KEY);
}

export async function getUserName(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(USER_NAME_KEY);
  } catch {
    return null;
  }
}

export async function setUserName(name: string): Promise<void> {
  await AsyncStorage.setItem(USER_NAME_KEY, name);
}

export async function getDeviceId(): Promise<string> {
  try {
    const existing = await AsyncStorage.getItem(DEVICE_ID_KEY);
    if (existing) return existing;
    const id = generateUUID();
    await AsyncStorage.setItem(DEVICE_ID_KEY, id);
    return id;
  } catch {
    return generateUUID();
  }
}

export async function isNamePrompted(): Promise<boolean> {
  try {
    const val = await AsyncStorage.getItem(NAME_PROMPTED_KEY);
    return val === 'true';
  } catch {
    return false;
  }
}

export async function setNamePrompted(): Promise<void> {
  await AsyncStorage.setItem(NAME_PROMPTED_KEY, 'true');
}
