import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api/client';
import { ProfileResponse, PredictionHistoryItem } from '../types/api';
import LoadingOverlay from '../components/LoadingOverlay';

const DEFAULT_USER_ID = 'farmer_001';

export default function ProfileScreen() {
  const [loading, setLoading] = useState(false);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [history, setHistory] = useState<PredictionHistoryItem[]>([]);
  const [editing, setEditing] = useState(false);

  // Form state
  const [name, setName] = useState('');
  const [phoneEmail, setPhoneEmail] = useState('');
  const [language, setLanguage] = useState('English');
  const [location, setLocation] = useState('');
  const [landArea, setLandArea] = useState('1');
  const [soilType, setSoilType] = useState('');
  const [preferredCrops, setPreferredCrops] = useState('');

  const loadProfile = async () => {
    setLoading(true);
    try {
      const p = await api.getProfile(DEFAULT_USER_ID);
      setProfile(p);
      setName(p.user.name);
      setPhoneEmail(p.user.phone_or_email);
      setLanguage(p.user.language);
      setLocation(p.user.location ?? '');
      setLandArea(String(p.farmer.land_area));
      setSoilType(p.farmer.soil_type ?? '');
      setPreferredCrops(p.farmer.preferred_crops ?? '');

      const hist = await api.getPredictionHistory(DEFAULT_USER_ID);
      setHistory(hist);
    } catch {
      // Profile doesn't exist yet — show form
      setEditing(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadProfile(); }, []);

  const saveProfile = async () => {
    if (!name.trim() || !phoneEmail.trim()) {
      Alert.alert('Validation', 'Name and phone/email are required.');
      return;
    }
    setLoading(true);
    try {
      await api.upsertProfile({
        user: {
          user_id: DEFAULT_USER_ID,
          name: name.trim(),
          phone_or_email: phoneEmail.trim(),
          language,
          location: location.trim() || undefined,
        },
        farmer: {
          farmer_id: `${DEFAULT_USER_ID}_farm`,
          user_id: DEFAULT_USER_ID,
          land_area: parseFloat(landArea) || 1,
          soil_type: soilType.trim() || undefined,
          preferred_crops: preferredCrops.trim() || undefined,
        },
      });
      setEditing(false);
      await loadProfile();
      Alert.alert('Success', 'Profile saved!');
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Failed to save profile.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <LoadingOverlay message="Loading profile…" />;

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.headerRow}>
          <Text style={styles.title}>My Profile</Text>
          {profile && !editing && (
            <TouchableOpacity onPress={() => setEditing(true)} style={styles.editBtn}>
              <Ionicons name="create-outline" size={20} color="#2E7D32" />
              <Text style={styles.editText}>Edit</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Profile form / view */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Personal Info</Text>
          <Field label="Name" value={name} onChange={setName} editable={editing} />
          <Field label="Phone / Email" value={phoneEmail} onChange={setPhoneEmail} editable={editing} keyboard="email-address" />
          <Field label="Language" value={language} onChange={setLanguage} editable={editing} />
          <Field label="Location" value={location} onChange={setLocation} editable={editing} placeholder="Village / City" />
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Farm Details</Text>
          <Field label="Land Area (ha)" value={landArea} onChange={setLandArea} editable={editing} keyboard="decimal-pad" />
          <Field label="Soil Type" value={soilType} onChange={setSoilType} editable={editing} placeholder="e.g. Black Cotton, Sandy Loam" />
          <Field label="Preferred Crops" value={preferredCrops} onChange={setPreferredCrops} editable={editing} placeholder="e.g. Groundnut, Cotton" />
        </View>

        {editing && (
          <TouchableOpacity style={styles.saveBtn} onPress={saveProfile} activeOpacity={0.85}>
            <Ionicons name="save-outline" size={20} color="#fff" />
            <Text style={styles.saveBtnText}>Save Profile</Text>
          </TouchableOpacity>
        )}

        {/* Prediction History */}
        {history.length > 0 && (
          <>
            <Text style={styles.sectionTitle}>Prediction History</Text>
            {history.map(item => (
              <View key={item.prediction_id} style={styles.histCard}>
                <View style={styles.histLeft}>
                  <Text style={styles.histCrop}>{item.crop ?? 'Multiple crops'}</Text>
                  <Text style={styles.histMeta}>{item.district} · {item.season} · {item.model_type}</Text>
                </View>
                <View style={styles.histRight}>
                  <Text style={styles.histValue}>{item.predicted_value.toFixed(2)}</Text>
                  <Text style={styles.histUnit}>t/ha</Text>
                </View>
              </View>
            ))}
          </>
        )}

        {!profile && !editing && (
          <TouchableOpacity style={styles.saveBtn} onPress={() => setEditing(true)} activeOpacity={0.85}>
            <Ionicons name="person-add-outline" size={20} color="#fff" />
            <Text style={styles.saveBtnText}>Create Profile</Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Field({
  label, value, onChange, editable, keyboard, placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  editable: boolean;
  keyboard?: any;
  placeholder?: string;
}) {
  return (
    <View style={styles.fieldRow}>
      <Text style={styles.fieldLabel}>{label}</Text>
      {editable ? (
        <TextInput
          style={styles.fieldInput}
          value={value}
          onChangeText={onChange}
          keyboardType={keyboard ?? 'default'}
          placeholder={placeholder ?? ''}
          placeholderTextColor="#BDBDBD"
        />
      ) : (
        <Text style={styles.fieldValue}>{value || '—'}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F1F8F2' },
  scroll: { padding: 20, paddingBottom: 40 },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  title: { fontSize: 24, fontWeight: '800', color: '#1B5E20' },
  editBtn: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  editText: { color: '#2E7D32', fontSize: 15, fontWeight: '600' },
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
  cardTitle: { fontSize: 13, fontWeight: '700', color: '#888', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  fieldRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#F5F5F5',
  },
  fieldLabel: { fontSize: 14, color: '#333', flex: 1 },
  fieldValue: { fontSize: 14, color: '#1B5E20', fontWeight: '600', flex: 1, textAlign: 'right' },
  fieldInput: {
    flex: 1,
    textAlign: 'right',
    fontSize: 14,
    color: '#222',
    borderBottomWidth: 1,
    borderBottomColor: '#A5D6A7',
    paddingBottom: 2,
  },
  saveBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#2E7D32',
    borderRadius: 14,
    paddingVertical: 16,
    marginBottom: 24,
    gap: 8,
  },
  saveBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: '#222', marginBottom: 10 },
  histCard: {
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 2,
    elevation: 1,
  },
  histLeft: { flex: 1 },
  histCrop: { fontSize: 14, fontWeight: '700', color: '#222' },
  histMeta: { fontSize: 12, color: '#888', marginTop: 3 },
  histRight: { alignItems: 'flex-end' },
  histValue: { fontSize: 18, fontWeight: '800', color: '#1B5E20' },
  histUnit: { fontSize: 11, color: '#888' },
});
