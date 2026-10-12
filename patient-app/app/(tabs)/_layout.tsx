import { Tabs } from 'expo-router';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../../constants/colors';

export default function TabLayout() {
  return (
    <Tabs screenOptions={{ 
      headerShown: true,
      tabBarActiveTintColor: COLORS.PRIMARY,
      tabBarInactiveTintColor: COLORS.TEXT_SECONDARY,
    }}>
      <Tabs.Screen 
        name="index" 
        options={{ 
          title: 'Home',
          tabBarIcon: ({ color }) => <Feather name="home" size={24} color={color} />
        }} 
      />
      <Tabs.Screen 
        name="chat/index" 
        options={{ 
          title: 'Consult',
          tabBarIcon: ({ color }) => <Feather name="message-circle" size={24} color={color} />
        }} 
      />
      <Tabs.Screen 
        name="records/index" 
        options={{ 
          title: 'Records',
          tabBarIcon: ({ color }) => <Feather name="file-text" size={24} color={color} />
        }} 
      />
      <Tabs.Screen 
        name="appointments/index" 
        options={{ 
          title: 'Visits',
          tabBarIcon: ({ color }) => <Feather name="calendar" size={24} color={color} />
        }} 
      />
      <Tabs.Screen 
        name="profile/index" 
        options={{ 
          title: 'Profile',
          tabBarIcon: ({ color }) => <Feather name="user" size={24} color={color} />
        }} 
      />

      {/* Sub-routes hidden from bottom tab bar */}
      <Tabs.Screen 
        name="chat/[id]" 
        options={{ 
          href: null,
          title: 'Consultation Detail',
        }} 
      />
      <Tabs.Screen 
        name="records/labs/index" 
        options={{ 
          href: null,
          title: 'Lab Results',
        }} 
      />
      <Tabs.Screen 
        name="records/medications" 
        options={{ 
          href: null,
          title: 'Medications',
        }} 
      />
      <Tabs.Screen 
        name="records/encounters" 
        options={{ 
          href: null,
          title: 'Clinical Notes',
        }} 
      />
      <Tabs.Screen 
        name="records/documents" 
        options={{ 
          href: null,
          title: 'Documents',
        }} 
      />
    </Tabs>
  );
}
