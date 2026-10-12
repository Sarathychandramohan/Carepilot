import { View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { useRouter } from 'expo-router';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../../../constants/colors';

export default function RecordsHubScreen() {
  const router = useRouter();
  
  const records = [
    { title: 'Lab Results', icon: 'activity', route: '/(tabs)/records/labs' },
    { title: 'Medications', icon: 'pill', route: '/(tabs)/records/medications' },
    { title: 'Clinical Notes', icon: 'file-text', route: '/(tabs)/records/encounters' },
    { title: 'Documents', icon: 'folder', route: '/(tabs)/records/documents' },
  ];

  return (
    <ScrollView className="flex-1 bg-background p-4">
      <Text className="text-xl font-bold text-textPrimary mb-4">Medical Records</Text>
      <View className="flex-row flex-wrap justify-between">
        {records.map((item, index) => (
          <TouchableOpacity 
            key={index} 
            className="bg-card w-[48%] aspect-square rounded-2xl p-4 mb-4 border border-border justify-center items-center shadow-sm"
            onPress={() => router.push(item.route as any)}
          >
            <View className="bg-primary/10 p-4 rounded-full mb-3">
              <Feather name={item.icon as any} size={32} color={COLORS.PRIMARY} />
            </View>
            <Text className="text-textPrimary font-semibold text-center">{item.title}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </ScrollView>
  );
}
