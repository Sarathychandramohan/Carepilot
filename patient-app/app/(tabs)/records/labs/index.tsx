import { View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { useState } from 'react';
import { useRouter } from 'expo-router';
import { useMockWorkflow } from '../../../../services/mock/mockWorkflow';
import { useAuthStore } from '../../../../store/authStore';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../../../../constants/colors';

const MOCK_LAB_TRENDS = [
  {
    testName: 'Creatinine',
    unit: 'mg/dL',
    referenceMin: 0.6,
    referenceMax: 1.2,
    latestValue: 1.4,
    latestDate: '2023-08-10',
    trendDirection: 'rising',
    readingsCount: 4,
    isOutOfRange: true,
    history: [
      { date: '2022-03-15', value: 1.1 },
      { date: '2022-09-20', value: 1.2 },
      { date: '2023-02-14', value: 1.3 },
      { date: '2023-08-10', value: 1.4 }
    ]
  },
  {
    testName: 'eGFR',
    unit: 'mL/min/1.73m2',
    referenceMin: 60,
    referenceMax: 120,
    latestValue: 47,
    latestDate: '2023-08-10',
    trendDirection: 'falling',
    readingsCount: 4,
    isOutOfRange: true,
    history: [
      { date: '2022-03-15', value: 58 },
      { date: '2022-09-20', value: 55 },
      { date: '2023-02-14', value: 51 },
      { date: '2023-08-10', value: 47 }
    ]
  },
  {
    testName: 'HbA1c',
    unit: '%',
    referenceMin: 4.0,
    referenceMax: 5.7,
    latestValue: 6.8,
    latestDate: '2023-07-01',
    trendDirection: 'stable',
    readingsCount: 3,
    isOutOfRange: true,
    history: [
      { date: '2022-06-10', value: 6.9 },
      { date: '2022-12-15', value: 6.7 },
      { date: '2023-07-01', value: 6.8 }
    ]
  }
];

export default function LabsScreen() {
  const [selectedTestIndex, setSelectedTestIndex] = useState(0);
  const submitConsultation = useMockWorkflow(s => s.submitConsultation);
  const user = useAuthStore(s => s.user);
  const router = useRouter();

  const currentTrend = MOCK_LAB_TRENDS[selectedTestIndex];

  const handleAskAboutTrend = async () => {
    const trendQuery = `Why has my ${currentTrend.testName} been ${currentTrend.trendDirection} over my last ${currentTrend.readingsCount} readings (most recent: ${currentTrend.latestValue} ${currentTrend.unit})?`;
    const id = await submitConsultation(trendQuery, user?.id || 'hero-001', `${user?.firstName || 'Christian'} ${user?.lastName || 'Labadie'}`);
    router.push(`/(tabs)/chat/${id}` as any);
  };

  return (
    <ScrollView className="flex-1 bg-background p-4">
      {/* Title */}
      <View className="mb-4">
        <Text className="text-2xl font-bold text-textPrimary">My Reports & Trends</Text>
        <Text className="text-textSecondary text-xs">Longitudinal lab readings & reference range analysis</Text>
      </View>

      {/* Test Selector Tabs */}
      <View className="flex-row space-x-2 mb-4 bg-card p-1.5 rounded-2xl border border-border">
        {MOCK_LAB_TRENDS.map((t, idx) => (
          <TouchableOpacity
            key={t.testName}
            onPress={() => setSelectedTestIndex(idx)}
            className={`flex-1 py-2 rounded-xl items-center ${
              selectedTestIndex === idx ? 'bg-primary' : 'bg-transparent'
            }`}
          >
            <Text className={`text-xs font-bold ${
              selectedTestIndex === idx ? 'text-white' : 'text-textSecondary'
            }`}>
              {t.testName}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* MODULE 3: Selected Test Card & Reference Range Highlight */}
      <View className="bg-card p-5 rounded-2xl border border-border mb-6 shadow-sm">
        <View className="flex-row items-center justify-between mb-3 pb-3 border-b border-border">
          <View>
            <Text className="text-textPrimary font-bold text-lg">{currentTrend.testName} Trend</Text>
            <Text className="text-textSecondary text-xs">Normal Range: {currentTrend.referenceMin} – {currentTrend.referenceMax} {currentTrend.unit}</Text>
          </View>
          <View className={`px-3 py-1 rounded-full ${
            currentTrend.isOutOfRange ? 'bg-urgent/10 border border-urgent/30' : 'bg-success/10'
          }`}>
            <Text className={`text-xs font-bold ${
              currentTrend.isOutOfRange ? 'text-urgent' : 'text-success'
            }`}>
              {currentTrend.latestValue} {currentTrend.unit} {currentTrend.isOutOfRange ? '(ABNORMAL)' : '(NORMAL)'}
            </Text>
          </View>
        </View>

        {/* 3+ Reading Trend Detection Flag Banner */}
        <View className={`p-3 rounded-xl mb-4 flex-row items-center justify-between ${
          currentTrend.trendDirection === 'rising' ? 'bg-urgent/10 border border-urgent/20' :
          currentTrend.trendDirection === 'falling' ? 'bg-warning/10 border border-warning/20' :
          'bg-primary/10 border border-primary/20'
        }`}>
          <View className="flex-row items-center">
            <Feather 
              name={currentTrend.trendDirection === 'rising' ? 'trending-up' : currentTrend.trendDirection === 'falling' ? 'trending-down' : 'minus'} 
              size={20} 
              color={currentTrend.trendDirection === 'rising' ? COLORS.URGENT : currentTrend.trendDirection === 'falling' ? COLORS.WARNING : COLORS.PRIMARY} 
              className="mr-2"
            />
            <View>
              <Text className="text-textPrimary font-bold text-xs uppercase">
                {currentTrend.trendDirection} Trend Detected ({currentTrend.readingsCount} Readings)
              </Text>
              <Text className="text-textSecondary text-[10px]">Flagged over 3+ consecutive lab results</Text>
            </View>
          </View>
        </View>

        {/* Longitudinal History Bars */}
        <Text className="text-textPrimary text-xs font-bold mb-3">Longitudinal History</Text>
        <View className="space-y-2 mb-4">
          {currentTrend.history.map((reading, idx) => (
            <View key={reading.date} className="flex-row items-center justify-between bg-background p-3 rounded-xl border border-border">
              <View className="flex-row items-center">
                <Text className="text-textSecondary text-xs font-mono w-24">{reading.date}</Text>
                <Text className="text-textPrimary text-xs font-bold ml-2">{reading.value} {currentTrend.unit}</Text>
              </View>
              {idx === currentTrend.history.length - 1 && (
                <View className="bg-primary/10 px-2 py-0.5 rounded">
                  <Text className="text-primary text-[10px] font-bold">LATEST</Text>
                </View>
              )}
            </View>
          ))}
        </View>

        {/* Disclaimer Note */}
        <View className="p-3 bg-gray-50 rounded-xl border border-border mb-4 flex-row items-start">
          <Feather name="info" size={14} color={COLORS.TEXT_SECONDARY} className="mr-2 mt-0.5" />
          <Text className="text-textSecondary text-[10px] flex-1 leading-4">
            CarePilot Display Aid: Trend flags are visual indicators only and do not generate medical commentary without doctor approval.
          </Text>
        </View>

        {/* MODULE 3: Ask CarePilot About This Trend Button */}
        <TouchableOpacity 
          onPress={handleAskAboutTrend}
          className="bg-primary py-3.5 px-4 rounded-xl flex-row items-center justify-center shadow-sm"
        >
          <Feather name="message-circle" size={16} color="white" className="mr-2" />
          <Text className="text-white font-bold text-xs">Ask CarePilot About This Trend</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}
