import { View, Text, ScrollView } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../../../constants/colors';

export default function EncountersScreen() {
  return (
    <ScrollView className="flex-1 bg-background p-4">
      <Text className="text-xl font-bold text-textPrimary mb-4">Clinical Notes & Encounters</Text>
      <View className="bg-card p-6 rounded-xl border border-border items-center justify-center py-10 shadow-sm">
        <Feather name="file-text" size={40} color={COLORS.TEXT_SECONDARY} className="mb-3" />
        <Text className="text-textPrimary font-semibold text-base mb-1">No clinical notes available</Text>
        <Text className="text-textSecondary text-xs text-center">Summary notes from your doctor visits will appear here.</Text>
      </View>
    </ScrollView>
  );
}
