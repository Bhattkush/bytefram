import { API_BASE_URL } from './config';
import {
  ProfileResponse,
  ProfileUpsertRequest,
  SmartRecommendRequest,
  SmartRecommendResponse,
  WeatherAlertRequest,
  WeatherAlertResponse,
  YieldPredictionRequest,
  YieldPredictionResponse,
  PredictionHistoryItem,
} from '../types/api';

export { API_BASE_URL };

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    let detail = body;
    try {
      const parsed = JSON.parse(body);
      detail = parsed.detail ?? parsed.message ?? body;
    } catch {}
    throw new Error(String(detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>('/health'),

  recommend: (payload: SmartRecommendRequest) =>
    request<SmartRecommendResponse>('/recommend', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  predictYield: (payload: YieldPredictionRequest) =>
    request<YieldPredictionResponse>('/predict-yield', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  weatherAlert: (payload: WeatherAlertRequest) =>
    request<WeatherAlertResponse>('/weather-alert', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /** Free fallback — uses Open-Meteo seasonal normals, no API key needed */
  climateData: (lat: number, lon: number) =>
    request<{
      district: string;
      season: string;
      source: string;
      current: Record<string, number | string>;
      alerts: Array<{ severity: string; title: string; action: string }>;
    }>(`/weather/climate?lat=${lat}&lon=${lon}`),

  upsertProfile: (payload: ProfileUpsertRequest) =>
    request<ProfileResponse>('/profile', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getProfile: (userId: string) =>
    request<ProfileResponse>(`/profile/${userId}`),

  getPredictionHistory: (userId: string, limit = 20) =>
    request<PredictionHistoryItem[]>(`/predictions/history/${userId}?limit=${limit}`),
};
