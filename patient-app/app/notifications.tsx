import { View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { useMockWorkflow } from '../services/mock/mockWorkflow';
import { useRouter } from 'expo-router';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../constants/colors';

export default function NotificationsScreen() {
  const notifications = useMockWorkflow(s => s.notifications);
  const markNotificationRead = useMockWorkflow(s => s.markNotificationRead);
  const router = useRouter();

  const handleNotificationPress = (n: typeof notifications[0]) => {
    markNotificationRead(n.id);
    if (n.relatedId) {
      router.push(`/(tabs)/chat/${n.relatedId}` as any);
    }
  };

  return (
    <View className="flex-1 bg-background">
      <View className="bg-card p-4 border-b border-border flex-row items-center justify-between">
        <View className="flex-row items-center">
          <TouchableOpacity onPress={() => router.back()} className="mr-3 p-1">
            <Feather name="arrow-left" size={20} color={COLORS.TEXT_PRIMARY} />
          </TouchableOpacity>
          <Text className="text-textPrimary font-bold text-lg">Notifications</Text>
        </View>
        <Text className="text-textSecondary text-xs">{notifications.length} total</Text>
      </View>

      <ScrollView className="flex-1 p-4">
        {notifications.length === 0 ? (
          <View className="items-center justify-center py-16">
            <Feather name="bell-off" size={40} color={COLORS.TEXT_SECONDARY} />
            <Text className="text-textSecondary font-medium text-sm mt-3">No notifications yet</Text>
          </View>
        ) : (
          notifications.map(n => (
            <TouchableOpacity
              key={n.id}
              onPress={() => handleNotificationPress(n)}
              className={`p-4 rounded-xl border mb-3 flex-row items-start ${
                !n.read 
                  ? 'bg-card border-primary/40' 
                  : 'bg-card/70 border-border'
              }`}
            >
              <View className={`p-2.5 rounded-full mr-3 ${
                n.category === 'consultation' ? 'bg-primary/10' : 'bg-secondary/10'
              }`}>
                <Feather 
                  name={n.category === 'consultation' ? 'message-square' : 'bell'} 
                  size={18} 
                  color={n.category === 'consultation' ? COLORS.PRIMARY : COLORS.SECONDARY} 
                />
              </View>
              <View className="flex-1">
                <View className="flex-row items-center justify-between">
                  <Text className={`text-sm ${!n.read ? 'font-bold text-textPrimary' : 'font-medium text-textPrimary'}`}>
                    {n.title}
                  </Text>
                  {!n.read && (
                    <View className="w-2 h-2 rounded-full bg-primary" />
                  )}
                </View>
                <Text className="text-textSecondary text-xs mt-1 leading-5">{n.body}</Text>
                <Text className="text-textSecondary text-[10px] mt-2">
                  {new Date(n.createdAt).toLocaleString()}
                </Text>
              </View>
            </TouchableOpacity>
          ))
        )}
      </ScrollView>
    </View>
  );
}
