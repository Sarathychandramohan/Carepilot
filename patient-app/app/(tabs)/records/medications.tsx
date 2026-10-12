import { View, Text, ScrollView } from 'react-native';
import { useAuthStore } from '../../../store/authStore';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../../../constants/colors';

export default function MedicationsScreen() {
  const user = useAuthStore(s => s.user);

  return (
    <ScrollView className="flex-1 bg-background p-4">
      <Text className="text-xl font-bold text-textPrimary mb-4">Active Medications</Text>
      
      {user?.medications.map(med => (
        <View key={med.id} className="bg-card p-4 rounded-xl border border-border mb-3 shadow-sm">
          <View className="flex-row items-center justify-between mb-2">
            <View className="flex-row items-center">
              <Feather name="plus-square" size={20} color={COLORS.PRIMARY} className="mr-2" />
              <Text className="font-bold text-textPrimary text-lg">{med.name}</Text>
            </View>
            <View className="bg-success/10 px-2 py-1 rounded">
              <Text className="text-success text-xs font-medium">Active</Text>
            </View>
          </View>
          <Text className="text-textSecondary mb-1"><Text className="font-medium text-textPrimary">Dosage:</Text> {med.dosage}</Text>
          <Text className="text-textSecondary"><Text className="font-medium text-textPrimary">Frequency:</Text> {med.frequency}</Text>
        </View>
      ))}
    </ScrollView>
  );
}
