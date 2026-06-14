import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Switch,
  Alert,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Location from 'expo-location';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api/client';
import { SmartRecommendResponse } from '../types/api';
import CropCard from '../components/CropCard';
import AlertBanner from '../components/AlertBanner';
import LoadingOverlay from '../components/LoadingOverlay';

export default function RecommendScreen() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SmartRecommendResponse | null>(null);
  const [irrigated, setIrrigated] = useState(false);
  const [profitMode, setProfitMode] = useState(false);
  const [landSize, setLandSize] = useState('1');
  const [topN, setTopN] = useState('3');

  const getRecommendations = async () => {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission Denied', 'Location permission is required for recommendations.');
      return;
    }

    setLoading(true);
    setResult(null);
    try {
      const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const data = await api.recommend({
        lat: loc.coords.latitude,
        lon: loc.coords.longitude,
        land_size: parseFloat(landSize) || 1,
        irrigated,
        profit_mode: profitMode,
        top_n: parseInt(topN) || 3,
      });
      setResult(data);
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Failed to get recommendations. Is the server running?');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <LoadingOverlay message="Fetching weather & running ML model…" />;
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>Smart Crop Recommend</Text>
        <Text style={styles.subtitle}>Uses your GPS location to find the best crops for your district</Text>

        {/* Config */}
        <View style={styles.card}>
          <Row label="Land Size (hectares)">
            <TextInput
              style={styles.input}
              value={landSize}
              onChangeText={setLandSize}
              keyboardType="decimal-pad"
              placeholder="1.0"
            />
          </Row>
          <Row label="No. of crops to show">
            <TextInput
              style={styles.input}
              value={topN}
              onChangeText={setTopN}
              keyboardType="number-pad"
              placeholder="3"
            />
          </Row>
          <Row label="Irrigated land">
            <Switch value={irrigated} onValueChange={setIrrigated} trackColor={{ true: '#2E7D32' }} />
          </Row>
          <Row label="Profit mode (vs safe)">
            <Switch value={profitMode} onValueChange={setProfitMode} trackColor={{ true: '#1565C0' }} />
          </Row>
        </View>

        <TouchableOpacity style={styles.button} onPress={getRecommendations} activeOpacity={0.85}>
          <Ionicons name="navigate" size={20} color="#fff" />
          <Text style={styles.buttonText}>Get Recommendations</Text>
        </TouchableOpacity>

        {result && (
          <>
            {/* Summary */}
            {result.summary && (
              <View style={styles.summaryCard}>
                <Text style={styles.summaryTitle}>
                  {result.district} · {result.season}
                </Text>
                {result.one_line_decision ? (
                  <Text style={styles.oneLine}>{result.one_line_decision}</Text>
                ) : null}
                <View style={styles.summaryGrid}>
                  <SumStat label="Best Crop" value={result.summary.best_crop} />
                  <SumStat label="Suitability" value={result.summary.suitability} />
                  <SumStat label="Risk" value={result.summary.overall_risk} />
                  <SumStat label="Profit" value={result.summary.display_profit} />
                </View>
              </View>
            )}

            {/* Alerts */}
            {[...(result.alerts ?? []), ...(result.risk_alerts ?? [])].map((a, i) => (
              <AlertBanner key={i} item={a} />
            ))}

            {/* Recommendations */}
            <Text style={styles.sectionTitle}>
              Top {result.recommendations.length} Crops ({result.crops_evaluated} evaluated)
            </Text>
            {result.recommendations.map((item, i) => (
              <CropCard key={item.crop_name} item={item} rank={i + 1} />
            ))}

            {result.insight ? (
              <View style={styles.insightBox}>
                <Text style={styles.insightText}>{result.insight}</Text>
              </View>
            ) : null}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      {children}
    </View>
  );
}

function SumStat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.sumStat}>
      <Text style={styles.sumValue}>{value}</Text>
      <Text style={styles.sumLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F1F8F2' },
  scroll: { padding: 20, paddingBottom: 40 },
  title: { fontSize: 24, fontWeight: '800', color: '#1B5E20', marginBottom: 4 },
  subtitle: { fontSize: 13, color: '#666', marginBottom: 20 },
  card: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F0F0',
  },
  rowLabel: { fontSize: 14, color: '#333' },
  input: {
    borderWidth: 1,
    borderColor: '#DDD',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
    width: 100,
    fontSize: 14,
    textAlign: 'right',
    color: '#222',
  },
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#2E7D32',
    borderRadius: 14,
    paddingVertical: 16,
    marginBottom: 24,
    gap: 8,
  },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  summaryCard: {
    backgroundColor: '#1B5E20',
    borderRadius: 14,
    padding: 18,
    marginBottom: 16,
  },
  summaryTitle: { color: '#A5D6A7', fontSize: 13, marginBottom: 4 },
  oneLine: { color: '#fff', fontSize: 15, fontWeight: '600', marginBottom: 14, lineHeight: 22 },
  summaryGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  sumStat: { width: '46%' },
  sumValue: { color: '#fff', fontSize: 16, fontWeight: '700' },
  sumLabel: { color: '#A5D6A7', fontSize: 11, marginTop: 2 },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: '#222', marginBottom: 12 },
  insightBox: {
    backgroundColor: '#E8F5E9',
    borderRadius: 10,
    padding: 14,
    marginTop: 8,
  },
  insightText: { color: '#2E7D32', fontSize: 13, lineHeight: 20 },
});
