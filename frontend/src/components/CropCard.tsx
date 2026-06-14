import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { RecommendationItem } from '../types/api';

interface Props {
  item: RecommendationItem;
  rank: number;
}

const RISK_COLOR: Record<string, string> = {
  'Low Risk': '#2E7D32',
  'Medium Risk': '#F57F17',
  'High Risk': '#C62828',
};

export default function CropCard({ item, rank }: Props) {
  const riskColor = RISK_COLOR[item.risk_confidence] ?? '#757575';
  const suitabilityPct = Math.round(item.suitability_score * 100);

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.rankBadge}>
          <Text style={styles.rankText}>#{rank}</Text>
        </View>
        <View style={styles.titleBlock}>
          <Text style={styles.cropName}>{item.crop_name}</Text>
          <Text style={styles.category}>{item.category}</Text>
        </View>
        <View style={[styles.riskBadge, { backgroundColor: riskColor }]}>
          <Text style={styles.riskText}>{item.risk_confidence}</Text>
        </View>
      </View>

      <View style={styles.row}>
        <Stat label="Suitability" value={`${suitabilityPct}%`} />
        <Stat label="Yield" value={item.display_yield || `${item.yield_per_hectare.toFixed(1)} t/ha`} />
        {item.display_profit ? <Stat label="Profit" value={item.display_profit} /> : null}
      </View>

      <View style={styles.progressBar}>
        <View style={[styles.progressFill, { width: `${suitabilityPct}%` as any }]} />
      </View>

      {item.explanation?.farmer_tip ? (
        <Text style={styles.tip}>{item.explanation.farmer_tip}</Text>
      ) : item.reason ? (
        <Text style={styles.tip}>{item.reason}</Text>
      ) : null}
    </View>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 3,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  rankBadge: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#E8F5E9',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },
  rankText: { color: '#2E7D32', fontWeight: '700', fontSize: 14 },
  titleBlock: { flex: 1 },
  cropName: { fontSize: 17, fontWeight: '700', color: '#1A1A1A' },
  category: { fontSize: 12, color: '#757575', marginTop: 2 },
  riskBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  riskText: { color: '#fff', fontSize: 11, fontWeight: '600' },
  row: { flexDirection: 'row', justifyContent: 'space-around', marginBottom: 10 },
  stat: { alignItems: 'center' },
  statValue: { fontSize: 15, fontWeight: '700', color: '#1B5E20' },
  statLabel: { fontSize: 11, color: '#9E9E9E', marginTop: 2 },
  progressBar: {
    height: 4,
    backgroundColor: '#E0E0E0',
    borderRadius: 2,
    marginBottom: 10,
    overflow: 'hidden',
  },
  progressFill: { height: '100%', backgroundColor: '#4CAF50', borderRadius: 2 },
  tip: { fontSize: 13, color: '#555', lineHeight: 18 },
});
