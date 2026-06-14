import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Location from 'expo-location';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api/client';
import AlertBanner from '../components/AlertBanner';
import LoadingOverlay from '../components/LoadingOverlay';

interface WeatherData {
  district: string;
  season: string;
  source: string;
  current: {
    temperature?: number;
    temperature_min?: number;
    temperature_max?: number;
    humidity?: number;
    rainfall?: number;
    rainfall_1h?: number;
    wind_speed?: number;
    description?: string;
  };
  alerts: Array<{ severity: string; title?: string; type?: string; action?: string; message?: string }>;
}

export default function WeatherScreen() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<WeatherData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchWeather = async () => {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission Denied', 'Location access is needed to fetch weather data.');
      return;
    }

    setLoading(true);
    setData(null);
    setError(null);

    let coords: { latitude: number; longitude: number };
    try {
      const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      coords = loc.coords;
    } catch (e: any) {
      setError('Could not get GPS location: ' + (e?.message ?? 'unknown error'));
      setLoading(false);
      return;
    }

    // 1. Try live OpenWeather API first
    try {
      const res = await api.weatherAlert({ latitude: coords.latitude, longitude: coords.longitude });
      setData({
        district: 'Your Location',
        season: '',
        source: 'Live — OpenWeatherMap',
        current: {
          temperature: res.current.temperature as number,
          humidity: res.current.humidity as number,
          rainfall: res.current.rainfall_1h as number,
          description: res.current.description as string,
        },
        alerts: (res.alerts ?? []).map(a => ({
          severity: a.severity,
          title: a.type,
          action: a.message,
        })),
      });
      setLoading(false);
      return;
    } catch (_liveErr) {
      // Live API failed (no API key or network) — fall through to climate normals
    }

    // 2. Fallback: Open-Meteo seasonal normals (always free)
    try {
      const climate = await api.climateData(coords.latitude, coords.longitude);
      setData({
        district: climate.district,
        season: climate.season,
        source: climate.source,
        current: climate.current as WeatherData['current'],
        alerts: climate.alerts.map(a => ({
          severity: a.severity,
          title: a.title,
          action: a.action,
        })),
      });
    } catch (fallbackErr: any) {
      setError(fallbackErr?.message ?? 'Failed to load weather data. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <LoadingOverlay message="Fetching weather data…" />;

  const c = data?.current;

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>Weather</Text>
        <Text style={styles.subtitle}>Live conditions and seasonal farming risk alerts</Text>

        <TouchableOpacity style={styles.button} onPress={fetchWeather} activeOpacity={0.85}>
          <Ionicons name="refresh-circle-outline" size={22} color="#fff" />
          <Text style={styles.buttonText}>Load Weather Data</Text>
        </TouchableOpacity>

        {/* Error state */}
        {error && (
          <View style={styles.errorBox}>
            <Ionicons name="warning-outline" size={20} color="#C62828" />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {/* Data */}
        {data && (
          <>
            {/* Header */}
            <View style={styles.sourceRow}>
              <Ionicons name="radio-outline" size={14} color="#888" />
              <Text style={styles.sourceText}>{data.source}</Text>
            </View>

            {/* Current conditions card */}
            <View style={styles.weatherCard}>
              <View style={styles.locationRow}>
                <Ionicons name="location" size={16} color="#A5D6A7" />
                <Text style={styles.locationText}>
                  {data.district.charAt(0).toUpperCase() + data.district.slice(1)}
                  {data.season ? `  ·  ${data.season}` : ''}
                </Text>
              </View>

              {/* Big temperature */}
              {c?.temperature !== undefined && (
                <Text style={styles.bigTemp}>{Number(c.temperature).toFixed(1)}°C</Text>
              )}
              {c?.description ? (
                <Text style={styles.description}>{String(c.description)}</Text>
              ) : null}

              {/* Stat row */}
              <View style={styles.statsRow}>
                {c?.humidity !== undefined && (
                  <WeatherStat icon="water-outline" label="Humidity" value={`${Number(c.humidity).toFixed(0)}%`} />
                )}
                {c?.rainfall !== undefined && (
                  <WeatherStat icon="rainy-outline" label="Rainfall" value={`${Number(c.rainfall).toFixed(0)} mm`} />
                )}
                {c?.temperature_min !== undefined && (
                  <WeatherStat icon="thermometer-outline" label="Min" value={`${Number(c.temperature_min).toFixed(0)}°C`} />
                )}
                {c?.temperature_max !== undefined && (
                  <WeatherStat icon="thermometer-outline" label="Max" value={`${Number(c.temperature_max).toFixed(0)}°C`} />
                )}
                {c?.wind_speed !== undefined && (
                  <WeatherStat icon="speedometer-outline" label="Wind" value={`${Number(c.wind_speed).toFixed(1)} m/s`} />
                )}
              </View>
            </View>

            {/* Alerts */}
            {data.alerts.length > 0 ? (
              <>
                <Text style={styles.sectionTitle}>Farming Alerts ({data.alerts.length})</Text>
                {data.alerts.map((a, i) => (
                  <AlertBanner
                    key={i}
                    item={{
                      severity: a.severity,
                      icon: a.severity === 'critical' ? '🚨' : a.severity === 'warning' ? '⚠️' : 'ℹ️',
                      title: a.title ?? a.type ?? '',
                      action: a.action ?? a.message ?? '',
                    }}
                  />
                ))}
              </>
            ) : (
              <View style={styles.noAlerts}>
                <Ionicons name="checkmark-circle-outline" size={36} color="#4CAF50" />
                <Text style={styles.noAlertsText}>No alerts for your area</Text>
              </View>
            )}
          </>
        )}

        {!data && !error && !loading && (
          <View style={styles.emptyState}>
            <Ionicons name="cloud-outline" size={64} color="#B0BEC5" />
            <Text style={styles.emptyText}>Tap "Load Weather Data" to see conditions for your location</Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function WeatherStat({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Ionicons name={icon as any} size={18} color="#A5D6A7" />
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F1F8F2' },
  scroll: { padding: 20, paddingBottom: 40 },
  title: { fontSize: 24, fontWeight: '800', color: '#1B5E20', marginBottom: 4 },
  subtitle: { fontSize: 13, color: '#666', marginBottom: 20 },
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#E65100',
    borderRadius: 14,
    paddingVertical: 16,
    marginBottom: 20,
    gap: 8,
  },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  errorBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    backgroundColor: '#FFEBEE',
    borderRadius: 10,
    padding: 14,
    marginBottom: 16,
  },
  errorText: { flex: 1, color: '#C62828', fontSize: 13, lineHeight: 18 },
  sourceRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: 8 },
  sourceText: { fontSize: 12, color: '#888' },
  weatherCard: {
    backgroundColor: '#1B5E20',
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
  },
  locationRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 8 },
  locationText: { color: '#A5D6A7', fontSize: 13 },
  bigTemp: { color: '#fff', fontSize: 52, fontWeight: '800', marginBottom: 4 },
  description: { color: '#C8E6C9', fontSize: 14, textTransform: 'capitalize', marginBottom: 16 },
  statsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 16 },
  stat: { alignItems: 'center', minWidth: '28%' },
  statValue: { color: '#fff', fontSize: 16, fontWeight: '700', marginTop: 4 },
  statLabel: { color: '#A5D6A7', fontSize: 11, marginTop: 2 },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: '#222', marginBottom: 10 },
  noAlerts: { alignItems: 'center', padding: 24 },
  noAlertsText: { color: '#555', fontSize: 14, marginTop: 8 },
  emptyState: { alignItems: 'center', marginTop: 60, paddingHorizontal: 20 },
  emptyText: { color: '#9E9E9E', fontSize: 14, marginTop: 16, textAlign: 'center', lineHeight: 22 },
});
