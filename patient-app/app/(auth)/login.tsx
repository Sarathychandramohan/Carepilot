import { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, Alert } from 'react-native';
import { useAuthStore } from '../../store/authStore';

export default function LoginScreen() {
  const [email, setEmail] = useState('patient@carepilot.ai');
  const [password, setPassword] = useState('demo1234');
  const login = useAuthStore(s => s.login);

  const handleLogin = async () => {
    try {
      await login(email, password);
    } catch (e: any) {
      Alert.alert('Error', e.message);
    }
  };

  return (
    <View className="flex-1 justify-center px-6 bg-background">
      <Text className="text-3xl font-bold text-primary mb-8 text-center">CarePilot AI</Text>
      
      <View className="bg-card p-6 rounded-2xl shadow-sm border border-border">
        <Text className="text-lg font-semibold text-textPrimary mb-4">Patient Login</Text>
        
        <TextInput
          className="border border-border rounded-lg p-3 mb-4 text-textPrimary"
          placeholder="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
        />
        
        <TextInput
          className="border border-border rounded-lg p-3 mb-6 text-textPrimary"
          placeholder="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
        />
        
        <TouchableOpacity 
          className="bg-primary py-3 rounded-lg items-center"
          onPress={handleLogin}
        >
          <Text className="text-white font-semibold text-base">Sign In</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}
