import { View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { useAuthStore } from '../../store/authStore';
import { useMockWorkflow } from '../../services/mock/mockWorkflow';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../../constants/colors';
import { useRouter } from 'expo-router';

export default function HomeScreen() {
  const user = useAuthStore(s => s.user);
  const consultations = useMockWorkflow(s => s.consultations);
  const notifications = useMockWorkflow(s => s.notifications);
  const router = useRouter();

  const activeConsultation = consultations[0];
  const unreadNotifs = notifications.filter(n => !n.read).length;

  return (
    <ScrollView className="flex-1 bg-background p-4">
      {/* Top Header */}
      <View className="flex-row items-center justify-between mb-6">
        <View>
          <Text className="text-2xl font-bold text-textPrimary">Hello, {user?.firstName || 'Christian'}</Text>
          <Text className="text-textSecondary text-xs mt-0.5">How are you feeling today?</Text>
        </View>
        <TouchableOpacity 
          onPress={() => router.push('/notifications')}
          className="p-2.5 bg-card rounded-full border border-border relative"
        >
          <Feather name="bell" size={20} color={COLORS.TEXT_PRIMARY} />
          {unreadNotifs > 0 && (
            <View className="absolute -top-1 -right-1 bg-urgent w-4 h-4 rounded-full items-center justify-center">
              <Text className="text-white text-[10px] font-bold">{unreadNotifs}</Text>
            </View>
          )}
        </TouchableOpacity>
      </View>

      <TouchableOpacity 
        className="bg-primary p-4 rounded-xl flex-row items-center justify-between mb-6"
        onPress={() => router.push('/(tabs)/chat')}
      >
        <View>
          <Text className="text-white font-semibold text-lg">New Consultation</Text>
          <Text className="text-white/80 mt-1">Ask our AI for guidance</Text>
        </View>
        <Feather name="arrow-right" size={24} color="white" />
      </TouchableOpacity>

      {activeConsultation && (
        <View className="bg-card p-4 rounded-xl border border-border mb-6">
          <View className="flex-row items-center justify-between mb-2">
            <Text className="font-semibold text-textPrimary">Recent Consultation</Text>
            <View className={`px-2 py-1 rounded ${activeConsultation.status === 'doctor_review' ? 'bg-warning/20' : 'bg-success/20'}`}>
              <Text className={`text-xs ${activeConsultation.status === 'doctor_review' ? 'text-warning' : 'text-success'}`}>
                {activeConsultation.status.replace('_', ' ').toUpperCase()}
              </Text>
            </View>
          </View>
          <Text className="text-textSecondary mb-3" numberOfLines={2}>{activeConsultation.query}</Text>
          <TouchableOpacity onPress={() => router.push(`/(tabs)/chat/${activeConsultation.id}` as any)}>
            <Text className="text-primary font-medium">View Details</Text>
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  );
}
