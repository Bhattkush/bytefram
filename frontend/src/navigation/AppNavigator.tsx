import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';

import HomeScreen from '../screens/HomeScreen';
import RecommendScreen from '../screens/RecommendScreen';
import YieldScreen from '../screens/YieldScreen';
import WeatherScreen from '../screens/WeatherScreen';
import ProfileScreen from '../screens/ProfileScreen';

const Tab = createBottomTabNavigator();

const TAB_ICONS: Record<string, { active: string; inactive: string }> = {
  Home: { active: 'home', inactive: 'home-outline' },
  Recommend: { active: 'leaf', inactive: 'leaf-outline' },
  Yield: { active: 'bar-chart', inactive: 'bar-chart-outline' },
  Weather: { active: 'partly-sunny', inactive: 'partly-sunny-outline' },
  Profile: { active: 'person-circle', inactive: 'person-circle-outline' },
};

export default function AppNavigator() {
  return (
    <NavigationContainer>
      <Tab.Navigator
        screenOptions={({ route }) => ({
          headerShown: false,
          tabBarActiveTintColor: '#2E7D32',
          tabBarInactiveTintColor: '#9E9E9E',
          tabBarStyle: {
            borderTopWidth: 1,
            borderTopColor: '#E8F5E9',
            backgroundColor: '#fff',
            paddingBottom: 6,
            height: 60,
          },
          tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
          tabBarIcon: ({ focused, color, size }) => {
            const icons = TAB_ICONS[route.name] ?? TAB_ICONS.Home;
            const iconName = focused ? icons.active : icons.inactive;
            return <Ionicons name={iconName as any} size={size} color={color} />;
          },
        })}
      >
        <Tab.Screen name="Home" component={HomeScreen} />
        <Tab.Screen name="Recommend" component={RecommendScreen} options={{ tabBarLabel: 'Recommend' }} />
        <Tab.Screen name="Yield" component={YieldScreen} options={{ tabBarLabel: 'Yield' }} />
        <Tab.Screen name="Weather" component={WeatherScreen} />
        <Tab.Screen name="Profile" component={ProfileScreen} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
