import { View, Text, ScrollView, ActivityIndicator, TouchableOpacity, TextInput, KeyboardAvoidingView, Platform } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState, useEffect } from 'react';
import { useMockWorkflow } from '../../../services/mock/mockWorkflow';
import { useAuthStore } from '../../../store/authStore';
import { consultationApi } from '../../../services/api/consultationApi';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../../../constants/colors';

export default function ConsultationDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const consultation = useMockWorkflow(s => s.getConsultationById(id));
  const approveConsultation = useMockWorkflow(s => s.approveConsultation);
  const sendFollowUpReply = useMockWorkflow(s => s.sendFollowUpReply);
  const user = useAuthStore(s => s.user);
  const router = useRouter();
  
  const [followUpText, setFollowUpText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Poll backend for consultation delivery status (clinical HITL safe gate)
  useEffect(() => {
    if (!id || !user) return;

    let isMounted = true;
    const checkDelivery = async () => {
      try {
        const res = await consultationApi.getPatientConsultation(user.id, id);
        if (!isMounted) return;
        if (res && res.thread_status === 'delivered' && res.final_response) {
          approveConsultation(id, res.final_response);
        }
      } catch (err) {
        // Safe silent fail if offline or not yet delivered
      }
    };

    checkDelivery();
    const interval = setInterval(checkDelivery, 3500);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [id, user]);

  if (!consultation) {
    return (
      <View className="flex-1 items-center justify-center bg-background p-6">
        <Feather name="alert-circle" size={48} color={COLORS.TEXT_SECONDARY} />
        <Text className="text-textPrimary font-bold text-lg mt-4">Consultation Not Found</Text>
        <TouchableOpacity 
          className="mt-6 bg-primary px-6 py-3 rounded-xl"
          onPress={() => router.push('/(tabs)/chat')}
        >
          <Text className="text-white font-medium">Back to Consultations</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const handleSendFollowUp = async () => {
    if (!followUpText.trim() || isSubmitting) return;
    setIsSubmitting(true);
    const text = followUpText.trim();
    setFollowUpText('');

    try {
      await consultationApi.sendFollowUpReply(consultation.id, text);
    } catch (err) {
      console.warn('Backend follow-up failed, falling back to local workflow:', err);
    }

    await sendFollowUpReply(consultation.id, text);
    setIsSubmitting(false);
  };

  const renderStatusBanner = () => {
    switch (consultation.status) {
      case 'sending':
        return (
          <View className="bg-primary/10 p-4 rounded-2xl flex-row items-center mb-4 border border-primary/20">
            <ActivityIndicator size="small" color={COLORS.PRIMARY} className="mr-3" />
            <View className="flex-1">
              <Text className="text-primary font-bold text-sm">Sending Request...</Text>
              <Text className="text-textSecondary text-xs">Connecting to CarePilot clinical pipeline</Text>
            </View>
          </View>
        );
      case 'processing':
        return (
          <View className="bg-primary/10 p-4 rounded-2xl flex-row items-center mb-4 border border-primary/20">
            <ActivityIndicator size="small" color={COLORS.PRIMARY} className="mr-3" />
            <View className="flex-1">
              <Text className="text-primary font-bold text-sm">Analyzing Your Request...</Text>
              <Text className="text-textSecondary text-xs">Retrieving patient lab history & medical knowledge base</Text>
            </View>
          </View>
        );
      case 'doctor_review':
        return (
          <View className="bg-warning/10 p-4 rounded-2xl mb-4 border border-warning/30">
            <View className="flex-row items-center mb-2">
              <View className="bg-warning/20 p-2 rounded-full mr-2">
                <Feather name="clock" size={18} color={COLORS.WARNING} />
              </View>
              <View className="flex-1">
                <Text className="text-warning font-bold text-sm">
                  {consultation.threadStatus === 'patient_replied' ? 'Follow-Up Awaiting Doctor Review' : 'Waiting for Doctor Review'}
                </Text>
                <Text className="text-textSecondary text-xs">Doctor-in-the-Loop Human Oversight</Text>
              </View>
              <View className="bg-warning/20 px-2.5 py-1 rounded-full">
                <Text className="text-warning text-xs font-bold uppercase">{consultation.urgency || 'SOON'}</Text>
              </View>
            </View>
            <Text className="text-textPrimary text-xs leading-5 mt-1">
              {consultation.threadStatus === 'patient_replied'
                ? 'Your follow-up reply has re-entered the same conversation thread and routed to Dr. Amelia Smith for review.'
                : 'Your consultation request has been prepared with your recent lab records and assigned to Dr. Amelia Smith for review.'}
            </Text>
          </View>
        );
      case 'approved':
        return (
          <View className="bg-success/10 p-4 rounded-2xl mb-4 border border-success/30">
            <View className="flex-row items-center">
              <View className="bg-success/20 p-2 rounded-full mr-3">
                <Feather name="check-circle" size={20} color={COLORS.SUCCESS} />
              </View>
              <View className="flex-1">
                <Text className="text-success font-bold text-sm">Doctor Approved Response Available</Text>
                <Text className="text-textSecondary text-xs">Reviewed by Dr. Amelia Smith · Nephrologist</Text>
              </View>
            </View>
          </View>
        );
      default:
        return null;
    }
  };

  return (
    <KeyboardAvoidingView 
      className="flex-1 bg-background" 
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      <ScrollView className="flex-1 p-4">
        {/* Header Info & Multi-Turn Badge */}
        <View className="flex-row items-center justify-between mb-4 bg-card p-3.5 rounded-2xl border border-border">
          <View className="flex-row items-center">
            <Feather name="message-square" size={18} color={COLORS.PRIMARY} className="mr-2" />
            <Text className="text-textPrimary font-bold text-sm">Thread #{consultation.id}</Text>
          </View>
          <View className="flex-row items-center space-x-2">
            <View className={`px-2.5 py-0.5 rounded-full ${
              consultation.threadStatus === 'patient_replied' ? 'bg-purple-100' :
              consultation.status === 'approved' ? 'bg-success/20' : 'bg-warning/20'
            }`}>
              <Text className={`text-[11px] font-bold ${
                consultation.threadStatus === 'patient_replied' ? 'text-purple-700' :
                consultation.status === 'approved' ? 'text-success' : 'text-warning'
              }`}>
                {consultation.threadStatus === 'patient_replied' ? 'PATIENT REPLIED' :
                 consultation.status === 'approved' ? 'APPROVED' : 'AWAITING DOCTOR'}
              </Text>
            </View>
            <View className="bg-gray-100 px-2 py-0.5 rounded-md">
              <Text className="text-textSecondary text-[10px] font-bold">{consultation.messages?.length || 1} Turn{(consultation.messages?.length || 1) > 1 ? 's' : ''}</Text>
            </View>
          </View>
        </View>

        {/* Status Banner */}
        {renderStatusBanner()}
        
        {/* Multi-Turn Thread Messages Feed */}
        {(consultation.messages || []).map((msg, index) => (
          <View key={msg.id || index} className="mb-4">
            <View 
              className={`max-w-[85%] ${
                msg.role === 'patient' 
                  ? 'self-end bg-primary' 
                  : 'self-start bg-card border-2 border-success/40'
              } p-4 rounded-2xl ${
                msg.role === 'patient' ? 'rounded-br-none' : 'rounded-bl-none'
              }`}
            >
              <View className="flex-row items-center justify-between mb-1 pb-1 border-b border-white/20">
                <View className="flex-row items-center">
                  {msg.role === 'doctor' && (
                    <Feather name="shield" size={12} color={COLORS.SUCCESS} className="mr-1" />
                  )}
                  <Text className={`text-xs font-bold ${msg.role === 'patient' ? 'text-white' : 'text-success'}`}>
                    {msg.role === 'patient' ? 'You (Patient)' : 'Dr. Amelia Smith (Nephrologist)'}
                  </Text>
                </View>
                <Text className={`text-[10px] ${msg.role === 'patient' ? 'text-white/70' : 'text-textSecondary'}`}>
                  {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </Text>
              </View>
              <Text className={`text-sm leading-6 mt-1 ${msg.role === 'patient' ? 'text-white font-medium' : 'text-textPrimary'}`}>
                {msg.content}
              </Text>
              {msg.role === 'doctor' && (
                <View className="mt-2 pt-1.5 border-t border-success/20 flex-row items-center">
                  <Feather name="check-circle" size={12} color={COLORS.SUCCESS} className="mr-1" />
                  <Text className="text-success font-bold text-[10px] tracking-wide">✓ Reviewed by Doctor</Text>
                </View>
              )}
            </View>
          </View>
        ))}

        {/* Safety & Clinical Guardrail Note */}
        <View className="p-3 bg-card/60 rounded-xl border border-border/60 mb-6 flex-row items-start">
          <Feather name="info" size={14} color={COLORS.TEXT_SECONDARY} className="mr-2 mt-0.5" />
          <Text className="text-textSecondary text-[11px] flex-1 leading-4">
            CarePilot HITL Guardrail: Patient replies re-enter this same thread with full history passed to Doctor review. Nothing auto-sends without doctor approval.
          </Text>
        </View>
      </ScrollView>

      {/* MODULE 1: Multi-Turn Follow-up Reply Input Composer */}
      <View className="p-3 bg-card border-t border-border flex-row items-end">
        <TextInput
          className="flex-1 border border-border rounded-xl p-3 max-h-28 text-textPrimary bg-background mr-2 text-sm"
          placeholder="Type a follow-up reply in this thread..."
          value={followUpText}
          onChangeText={setFollowUpText}
          multiline
        />
        <TouchableOpacity 
          className={`h-11 w-11 rounded-xl items-center justify-center ${
            followUpText.trim() ? 'bg-primary' : 'bg-gray-300'
          }`}
          onPress={handleSendFollowUp}
          disabled={!followUpText.trim() || isSubmitting}
        >
          {isSubmitting ? (
            <ActivityIndicator size="small" color="white" />
          ) : (
            <Feather name="send" size={18} color="white" />
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}
