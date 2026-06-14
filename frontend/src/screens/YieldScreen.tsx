import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api/client';
import { YieldPredictionResponse } from '../types/api';
import LoadingOverlay from '../components/LoadingOverlay';

const DISTRICTS = [
  'Ahmedabad', 'Amreli', 'Anand', 'Aravalli', 'Banaskantha', 'Bharuch',
  'Bhavnagar', 'Botad', 'Chhotaudaipur', 'Dahod', 'Dang', 'Devbhumi Dwarka',
  'Gandhinagar', 'Gir Somnath', 'Jamnagar', 'Junagadh', 'Kheda', 'Kutch',
  'Mahisagar', 'Mehsana', 'Morbi', 'Narmada', 'Navsari', 'Panchmahal',
  'Patan', 'Porbandar', 'Rajkot', 'Sabarkantha', 'Surat', 'Surendranagar',
  'Tapi', 'Vadodara', 'Valsad',
];

const SEASONS = ['Kharif', 'Rabi', 'Summer'];

const CROPS = [
  'Groundnut', 'Cotton', 'Wheat', 'Rice', 'Bajra', 'Maize', 'Jowar',
  'Tur', 'Moong', 'Urad', 'Castor', 'Sesame', 'Mustard', 'Cumin',
  'Fennel', 'Garlic', 'Onion', 'Potato', 'Banana', 'Mango',
];

interface FormState {
  district: string;
  season: string;
  crop: string;
  year: string;
  temperature_avg: string;
  temperature_min: string;
  temperature_max: string;
  rainfall: string;
  humidity: string;
}

const DEFAULT_FORM: FormState = {
  district: 'Ahmedabad',
  season: 'Kharif',
  crop: 'Groundnut',
  year: String(new Date().getFullYear()),
  temperature_avg: '28',
  temperature_min: '20',
  temperature_max: '36',
  rainfall: '500',
  humidity: '65',
};

export default function YieldScreen() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<YieldPredictionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pickerType, setPickerType] = useState<'district' | 'season' | 'crop' | null>(null);

  const set = (key: keyof FormState) => (val: string) =>
    setForm(prev => ({ ...prev, [key]: val }));

  const predict = async () => {
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const res = await api.predictYield({
        district: form.district,
        season: form.season,
        crop: form.crop,
        year: parseInt(form.year) || new Date().getFullYear(),
        temperature_avg: parseFloat(form.temperature_avg) || 28,
        temperature_min: parseFloat(form.temperature_min) || 20,
        temperature_max: parseFloat(form.temperature_max) || 36,
        rainfall: parseFloat(form.rainfall) || 500,
        humidity: parseFloat(form.humidity) || 65,
      });
      setResult(res);
    } catch (err: any) {
      setError(err?.message ?? 'Prediction failed. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <LoadingOverlay message="Running yield model…" />;

  if (pickerType) {
    const options = pickerType === 'district' ? DISTRICTS : pickerType === 'season' ? SEASONS : CROPS;
    return (
      <SafeAreaView style={styles.safe}>
        <ScrollView contentContainerStyle={styles.scroll}>
          <TouchableOpacity style={styles.backBtn} onPress={() => setPickerType(null)}>
            <Ionicons name="arrow-back" size={20} color="#2E7D32" />
            <Text style={styles.backText}>Back</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Select {pickerType}</Text>
          {options.map(opt => (
            <TouchableOpacity
              key={opt}
              style={[styles.optionRow, form[pickerType] === opt && styles.optionSelected]}
              onPress={() => { set(pickerType)(opt); setPickerType(null); }}
            >
              <Text style={[styles.optionText, form[pickerType] === opt && styles.optionTextSelected]}>
                {opt}
              </Text>
              {form[pickerType] === opt && <Ionicons name="checkmark" size={18} color="#fff" />}
            </TouchableOpacity>
          ))}
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>Yield Prediction</Text>
        <Text style={styles.subtitle}>Enter field details to predict crop yield</Text>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Location & Crop</Text>
          <SelectRow label="District" value={form.district} onPress={() => setPickerType('district')} />
          <SelectRow label="Season" value={form.season} onPress={() => setPickerType('season')} />
          <SelectRow label="Crop" value={form.crop} onPress={() => setPickerType('crop')} />
          <InputRow label="Year" value={form.year} onChange={set('year')} keyboard="number-pad" />
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Weather Conditions</Text>
          <InputRow label="Avg Temp (°C)" value={form.temperature_avg} onChange={set('temperature_avg')} keyboard="decimal-pad" />
          <InputRow label="Min Temp (°C)" value={form.temperature_min} onChange={set('temperature_min')} keyboard="decimal-pad" />
          <InputRow label="Max Temp (°C)" value={form.temperature_max} onChange={set('temperature_max')} keyboard="decimal-pad" />
          <InputRow label="Rainfall (mm)" value={form.rainfall} onChange={set('rainfall')} keyboard="decimal-pad" />
          <InputRow label="Humidity (%)" value={form.humidity} onChange={set('humidity')} keyboard="decimal-pad" />
        </View>

        <TouchableOpacity style={styles.button} onPress={predict} activeOpacity={0.85}>
          <Ionicons name="analytics" size={20} color="#fff" />
          <Text style={styles.buttonText}>Predict Yield</Text>
        </TouchableOpacity>

        {error && (
          <View style={styles.errorBox}>
            <Ionicons name="warning-outline" size={20} color="#C62828" />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {result && (
          <View style={styles.resultCard}>
            <Text style={styles.resultLabel}>Predicted Yield</Text>
            <Text style={styles.resultValue}>
              {result.predicted_yield_ton_per_hectare.toFixed(2)}{' '}
              <Text style={styles.resultUnit}>tonnes / hectare</Text>
            </Text>
            <View style={styles.resultMeta}>
              <MetaItem icon="leaf-outline" text={result.crop} />
              <MetaItem icon="location-outline" text={result.district} />
              <MetaItem icon="calendar-outline" text={result.season} />
            </View>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function SelectRow({ label, value, onPress }: { label: string; value: string; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.row} onPress={onPress}>
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={styles.selectValue}>
        <Text style={styles.selectText}>{value}</Text>
        <Ionicons name="chevron-forward" size={16} color="#999" />
      </View>
    </TouchableOpacity>
  );
}

function InputRow({
  label, value, onChange, keyboard,
}: {
  label: string; value: string; onChange: (v: string) => void; keyboard: any;
}) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <TextInput
        style={styles.input}
        value={value}
        onChangeText={onChange}
        keyboardType={keyboard}
        placeholder="0"
      />
    </View>
  );
}

function MetaItem({ icon, text }: { icon: string; text: string }) {
  return (
    <View style={styles.metaItem}>
      <Ionicons name={icon as any} size={14} color="#A5D6A7" />
      <Text style={styles.metaText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F1F8F2' },
  scroll: { padding: 20, paddingBottom: 40 },
  title: { fontSize: 24, fontWeight: '800', color: '#1B5E20', marginBottom: 4 },
  subtitle: { fontSize: 13, color: '#666', marginBottom: 20 },
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
  cardTitle: { fontSize: 14, fontWeight: '700', color: '#555', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#F5F5F5',
  },
  rowLabel: { fontSize: 14, color: '#333' },
  selectValue: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  selectText: { fontSize: 14, color: '#2E7D32', fontWeight: '600' },
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
    backgroundColor: '#1565C0',
    borderRadius: 14,
    paddingVertical: 16,
    marginBottom: 24,
    gap: 8,
  },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  resultCard: {
    backgroundColor: '#1B5E20',
    borderRadius: 14,
    padding: 20,
    alignItems: 'center',
  },
  resultLabel: { color: '#A5D6A7', fontSize: 13, marginBottom: 8 },
  resultValue: { color: '#fff', fontSize: 36, fontWeight: '800' },
  resultUnit: { fontSize: 16, fontWeight: '400' },
  resultMeta: { flexDirection: 'row', gap: 16, marginTop: 16 },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaText: { color: '#A5D6A7', fontSize: 12 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 16 },
  backText: { color: '#2E7D32', fontSize: 15 },
  optionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 2,
    elevation: 1,
  },
  optionSelected: { backgroundColor: '#2E7D32' },
  optionText: { fontSize: 15, color: '#333' },
  optionTextSelected: { color: '#fff', fontWeight: '600' },
});
