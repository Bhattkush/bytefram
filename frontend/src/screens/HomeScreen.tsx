import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { api } from '../api/client';

const CURRENT_SEASON = (() => {
  const m = new Date().getMonth() + 1;
  if (m >= 6 && m <= 10) return 'Kharif';
  if (m >= 11 || m <= 2) return 'Rabi';
  return 'Summer';
})();

export default function HomeScreen() {
  const navigation = useNavigation<any>();
  const [serverStatus, setServerStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [refreshing, setRefreshing] = useState(false);

  const checkHealth = async () => {
    try {
      await api.health();
      setServerStatus('online');
    } catch {
      setServerStatus('offline');
    }
  };

  useEffect(() => { checkHealth(); }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await checkHealth();
    setRefreshing(false);
  };

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#2E7D32" />}
      >
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.greeting}>Welcome to</Text>
            <Text style={styles.appName}>ByteFarm AI</Text>
            <Text style={styles.subtitle}>Crop Yield Prediction & Planning</Text>
          </View>
          <View style={[styles.statusDot, { backgroundColor: serverStatus === 'online' ? '#4CAF50' : serverStatus === 'offline' ? '#F44336' : '#FFC107' }]} />
        </View>

        {/* Season card */}
        <View style={styles.seasonCard}>
          <Ionicons name="leaf-outline" size={28} color="#fff" />
          <View style={styles.seasonText}>
            <Text style={styles.seasonLabel}>Current Season</Text>
            <Text style={styles.seasonValue}>{CURRENT_SEASON}</Text>
          </View>
        </View>

        {/* Quick Actions */}
        <Text style={styles.sectionTitle}>Quick Actions</Text>
        <View style={styles.grid}>
          <QuickAction
            icon="navigate-circle-outline"
            label="Smart Recommend"
            color="#1B5E20"
            onPress={() => navigation.navigate('Recommend')}
          />
          <QuickAction
            icon="bar-chart-outline"
            label="Predict Yield"
            color="#1565C0"
            onPress={() => navigation.navigate('Yield')}
          />
          <QuickAction
            icon="partly-sunny-outline"
            label="Weather Alerts"
            color="#E65100"
            onPress={() => navigation.navigate('Weather')}
          />
          <QuickAction
            icon="person-circle-outline"
            label="My Profile"
            color="#4A148C"
            onPress={() => navigation.navigate('Profile')}
          />
        </View>

        {/* Info cards */}
        <Text style={styles.sectionTitle}>About This App</Text>
        <InfoCard
          icon="analytics-outline"
          title="ML-Powered Predictions"
          body="Uses historical weather, soil, and satellite (NDVI) data to predict crop yield for Gujarat districts."
        />
        <InfoCard
          icon="earth-outline"
          title="GPS-Based Recommendations"
          body="Share your location and get instant crop recommendations tailored to your nearest district."
        />
        <InfoCard
          icon="shield-checkmark-outline"
          title="Risk Analysis"
          body="Understand drought, heat, and flood risk before planting so you can make informed decisions."
        />
      </ScrollView>
    </SafeAreaView>
  );
}

function QuickAction({
  icon, label, color, onPress,
}: {
  icon: string; label: string; color: string; onPress: () => void;
}) {
  return (
    <TouchableOpacity style={styles.actionCard} onPress={onPress} activeOpacity={0.8}>
      <View style={[styles.actionIcon, { backgroundColor: color }]}>
        <Ionicons name={icon as any} size={26} color="#fff" />
      </View>
      <Text style={styles.actionLabel}>{label}</Text>
    </TouchableOpacity>
  );
}

function InfoCard({ icon, title, body }: { icon: string; title: string; body: string }) {
  return (
    <View style={styles.infoCard}>
      <Ionicons name={icon as any} size={22} color="#2E7D32" style={{ marginRight: 12 }} />
      <View style={{ flex: 1 }}>
        <Text style={styles.infoTitle}>{title}</Text>
        <Text style={styles.infoBody}>{body}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F1F8F2' },
  scroll: { padding: 20, paddingBottom: 40 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 20,
  },
  greeting: { fontSize: 14, color: '#555' },
  appName: { fontSize: 28, fontWeight: '800', color: '#1B5E20' },
  subtitle: { fontSize: 13, color: '#666', marginTop: 2 },
  statusDot: { width: 12, height: 12, borderRadius: 6, marginTop: 6 },
  seasonCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#2E7D32',
    borderRadius: 14,
    padding: 18,
    marginBottom: 24,
  },
  seasonText: { marginLeft: 14 },
  seasonLabel: { color: '#A5D6A7', fontSize: 13 },
  seasonValue: { color: '#fff', fontSize: 22, fontWeight: '700' },
  sectionTitle: { fontSize: 17, fontWeight: '700', color: '#1A1A1A', marginBottom: 12 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 },
  actionCard: {
    width: '47%',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  actionIcon: { width: 50, height: 50, borderRadius: 14, justifyContent: 'center', alignItems: 'center', marginBottom: 10 },
  actionLabel: { fontSize: 13, fontWeight: '600', color: '#333', textAlign: 'center' },
  infoCard: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    alignItems: 'flex-start',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 1,
  },
  infoTitle: { fontSize: 14, fontWeight: '600', color: '#222', marginBottom: 4 },
  infoBody: { fontSize: 13, color: '#666', lineHeight: 18 },
});
