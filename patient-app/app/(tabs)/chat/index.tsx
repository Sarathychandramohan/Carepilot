import { View, Text, ScrollView, TextInput, TouchableOpacity, KeyboardAvoidingView, Platform } from 'react-native';
import { useState } from 'react';
import { useAuthStore } from '../../../store/authStore';
import { useMockWorkflow } from '../../../services/mock/mockWorkflow';
import { useRouter } from 'expo-router';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../../../constants/colors';

export default function ChatScreen() {
  const [query, setQuery] = useState('');
  const user = useAuthStore(s => s.user);
  const submitConsultation = useMockWorkflow(s => s.submitConsultation);
  const router = useRouter();

  const handleSend = async () => {
    if (!query.trim() || !user) return;
    
    const id = await submitConsultation(query, user.id, `${user.firstName} ${user.lastName}`);
    setQuery('');
    router.push(`/(tabs)/chat/${id}` as any);
  };

  return (
    <KeyboardAvoidingView 
      className="flex-1 bg-background" 
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      <ScrollView className="flex-1 p-4">
        <View className="bg-card p-4 rounded-xl border border-border mb-4">
          <Text className="text-textPrimary font-semibold mb-2">CarePilot AI Assistant</Text>
          <Text className="text-textSecondary">Describe your symptoms or ask a question about your health. I will analyze it and prepare a report for your doctor.</Text>
        </View>
      </ScrollView>
      
      <View className="p-4 bg-card border-t border-border flex-row items-end">
        <TextInput
          className="flex-1 border border-border rounded-xl p-3 max-h-32 text-textPrimary bg-background mr-2"
          placeholder="Describe your issue..."
          value={query}
          onChangeText={setQuery}
          multiline
        />
        <TouchableOpacity 
          className="bg-primary h-12 w-12 rounded-xl items-center justify-center"
          onPress={handleSend}
          disabled={!query.trim()}
        >
          <Feather name="send" size={20} color="white" />
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}
