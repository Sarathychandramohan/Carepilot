import { View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { useAuthStore } from '../../../store/authStore';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../../../constants/colors';

export default function ProfileScreen() {
  const { user, logout } = useAuthStore();

  return (
    <ScrollView className="flex-1 bg-background p-4">
      <View className="bg-card p-6 rounded-xl border border-border mb-6 items-center">
        <View className="bg-primary/10 w-20 h-20 rounded-full items-center justify-center mb-4">
          <Text className="text-primary text-2xl font-bold">{user?.firstName.charAt(0)}{user?.lastName.charAt(0)}</Text>
        </View>
        <Text className="text-xl font-bold text-textPrimary">{user?.firstName} {user?.lastName}</Text>
        <Text className="text-textSecondary">ID: {user?.id}</Text>
      </View>

      <View className="bg-card rounded-xl border border-border mb-6 overflow-hidden">
        <View className="p-4 border-b border-border">
          <Text className="font-semibold text-textPrimary">Personal Information</Text>
        </View>
        <View className="p-4">
          <View className="flex-row justify-between mb-3">
            <Text className="text-textSecondary">Date of Birth</Text>
            <Text className="text-textPrimary font-medium">{user?.dateOfBirth}</Text>
          </View>
          <View className="flex-row justify-between mb-3">
            <Text className="text-textSecondary">Gender</Text>
            <Text className="text-textPrimary font-medium">{user?.gender === 'M' ? 'Male' : 'Female'}</Text>
          </View>
          <View className="flex-row justify-between">
            <Text className="text-textSecondary">Age</Text>
            <Text className="text-textPrimary font-medium">{user?.age} years</Text>
          </View>
        </View>
      </View>

      <TouchableOpacity 
        className="bg-card p-4 rounded-xl border border-urgent items-center flex-row justify-center mb-8"
        onPress={logout}
      >
        <Feather name="log-out" size={20} color={COLORS.URGENT} className="mr-2" />
        <Text className="text-urgent font-semibold">Sign Out</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}
