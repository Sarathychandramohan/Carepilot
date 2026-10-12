import { View, Text, ScrollView } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../../../constants/colors';

export default function DocumentsScreen() {
  return (
    <ScrollView className="flex-1 bg-background p-4">
      <Text className="text-xl font-bold text-textPrimary mb-4">Medical Documents</Text>
      <View className="bg-card p-6 rounded-xl border border-border items-center justify-center py-10 shadow-sm">
        <Feather name="folder" size={40} color={COLORS.TEXT_SECONDARY} className="mb-3" />
        <Text className="text-textPrimary font-semibold text-base mb-1">No documents uploaded</Text>
        <Text className="text-textSecondary text-xs text-center">Uploaded medical records and care plans will appear here.</Text>
      </View>
    </ScrollView>
  );
}
