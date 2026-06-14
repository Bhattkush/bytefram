import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { AlertItem } from '../types/api';

const SEVERITY_COLORS: Record<string, { bg: string; text: string }> = {
  critical: { bg: '#FFEBEE', text: '#C62828' },
  warning: { bg: '#FFF8E1', text: '#F57F17' },
  info: { bg: '#E3F2FD', text: '#1565C0' },
};

export default function AlertBanner({ item }: { item: AlertItem }) {
  const colors = SEVERITY_COLORS[item.severity] ?? SEVERITY_COLORS.info;
  return (
    <View style={[styles.banner, { backgroundColor: colors.bg }]}>
      <Text style={styles.icon}>{item.icon}</Text>
      <View style={styles.body}>
        <Text style={[styles.title, { color: colors.text }]}>{item.title}</Text>
        {item.action ? <Text style={styles.action}>{item.action}</Text> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    borderRadius: 10,
    padding: 12,
    marginBottom: 8,
  },
  icon: { fontSize: 20, marginRight: 10 },
  body: { flex: 1 },
  title: { fontSize: 14, fontWeight: '600' },
  action: { fontSize: 12, color: '#555', marginTop: 4 },
});
