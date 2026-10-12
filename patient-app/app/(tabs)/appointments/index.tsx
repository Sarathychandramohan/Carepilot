import { View, Text, ScrollView, TouchableOpacity, Modal, TextInput, ActivityIndicator } from 'react-native';
import { useState } from 'react';
import { useMockWorkflow } from '../../../services/mock/mockWorkflow';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../../../constants/colors';
import { AppointmentRequest, Appointment } from '../../../types';

export default function AppointmentsScreen() {
  const appointments = useMockWorkflow(s => s.appointments);
  const appointmentRequests = useMockWorkflow(s => s.appointmentRequests);
  const requestReschedule = useMockWorkflow(s => s.requestRescheduleAppointment);

  const [selectedAppointmentId, setSelectedAppointmentId] = useState<string | null>(null);
  const [rescheduleModalVisible, setRescheduleModalVisible] = useState(false);
  const [newDate, setNewDate] = useState('2023-10-22');
  const [newTime, setNewTime] = useState('11:00 AM');
  const [reasonText, setReasonText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleOpenReschedule = (apptId: string) => {
    setSelectedAppointmentId(apptId);
    setRescheduleModalVisible(true);
  };

  const handleSubmitReschedule = async () => {
    if (!selectedAppointmentId || !reasonText.trim()) return;
    setIsSubmitting(true);
    await requestReschedule(selectedAppointmentId, newDate, newTime, reasonText.trim());
    setIsSubmitting(false);
    setRescheduleModalVisible(false);
    setReasonText('');
  };

  return (
    <ScrollView className="flex-1 bg-background p-4">
      {/* Header */}
      <View className="mb-4">
        <Text className="text-2xl font-bold text-textPrimary">Visits & Scheduling</Text>
        <Text className="text-textSecondary text-xs">Manage appointments & request reschedules</Text>
      </View>

      {/* MODULE 2: Follow-up Reminder Banner */}
      <View className="bg-primary/10 p-4 rounded-2xl border border-primary/20 mb-6 flex-row items-center">
        <View className="bg-primary/20 p-2.5 rounded-full mr-3">
          <Feather name="bell" size={20} color={COLORS.PRIMARY} />
        </View>
        <View className="flex-1">
          <Text className="text-primary font-bold text-sm">Follow-up Reminder</Text>
          <Text className="text-textPrimary text-xs mt-0.5">Your nephrology checkup with Dr. Amelia Smith is in 3 days (Oct 15 at 10:00 AM).</Text>
        </View>
      </View>

      {/* Pending Reschedule / New Requests Section (HITL Pattern) */}
      {appointmentRequests.length > 0 && (
        <View className="mb-6">
          <Text className="text-sm font-bold text-textPrimary uppercase tracking-wider mb-3">Pending Doctor Approval</Text>
          {appointmentRequests.map((req: AppointmentRequest) => (
            <View key={req.id} className="bg-card p-4 rounded-2xl border-2 border-warning/40 mb-3 shadow-sm">
              <View className="flex-row items-center justify-between mb-2">
                <View className="flex-row items-center">
                  <Feather name="clock" size={16} color={COLORS.WARNING} className="mr-2" />
                  <Text className="font-bold text-textPrimary text-xs uppercase">
                    {req.requestType === 'reschedule' ? 'Reschedule Request' : 'New Appointment Request'}
                  </Text>
                </View>
                <View className="bg-warning/20 px-2.5 py-0.5 rounded-full">
                  <Text className="text-warning text-[10px] font-bold">AWAITING DOCTOR</Text>
                </View>
              </View>

              <Text className="text-textPrimary text-sm font-semibold mb-1">Requested Date: {req.requestedDate} at {req.requestedTime}</Text>
              <Text className="text-textSecondary text-xs leading-4">Reason: {req.reason}</Text>

              <View className="mt-3 pt-2 border-t border-border flex-row items-center">
                <Feather name="info" size={12} color={COLORS.TEXT_SECONDARY} className="mr-1" />
                <Text className="text-textSecondary text-[10px]">Route to Dr. Amelia Smith for approval. Not auto-confirmed.</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* Upcoming Appointments List */}
      <View className="mb-6">
        <Text className="text-sm font-bold text-textPrimary uppercase tracking-wider mb-3">Scheduled Appointments</Text>

        {appointments.map((appt: Appointment) => (
          <View key={appt.id} className="bg-card p-4 rounded-2xl border border-border mb-3 shadow-sm">
            <View className="flex-row items-center justify-between mb-2">
              <View className="flex-row items-center">
                <Feather name="calendar" size={16} color={COLORS.PRIMARY} className="mr-2" />
                <Text className="font-bold text-textPrimary text-sm">{appt.date} at {appt.time}</Text>
              </View>
              <View className={`px-2.5 py-0.5 rounded-full ${
                appt.status === 'confirmed' ? 'bg-success/20' : 'bg-gray-100'
              }`}>
                <Text className={`text-[10px] font-bold uppercase ${
                  appt.status === 'confirmed' ? 'text-success' : 'text-textSecondary'
                }`}>
                  {appt.status}
                </Text>
              </View>
            </View>

            <Text className="text-textPrimary text-xs font-medium mb-1">{appt.reason} · {appt.doctorName}</Text>
            
            {/* MODULE 2: Request Reschedule Action Button */}
            {appt.status !== 'completed' && (
              <TouchableOpacity 
                onPress={() => handleOpenReschedule(appt.id)}
                className="mt-3 py-2 px-3 bg-background rounded-xl border border-border flex-row items-center justify-center"
              >
                <Feather name="rotate-cw" size={14} color={COLORS.PRIMARY} className="mr-1.5" />
                <Text className="text-primary text-xs font-bold">Request Reschedule</Text>
              </TouchableOpacity>
            )}
          </View>
        ))}
      </View>

      {/* MODULE 2: Reschedule Request Modal */}
      <Modal visible={rescheduleModalVisible} transparent animationType="slide">
        <View className="flex-1 bg-black/50 justify-end">
          <View className="bg-card p-5 rounded-t-3xl border-t border-border space-y-4">
            <View className="flex-row items-center justify-between pb-3 border-b border-border">
              <Text className="text-textPrimary font-bold text-base">Request Reschedule</Text>
              <TouchableOpacity onPress={() => setRescheduleModalVisible(false)}>
                <Feather name="x" size={20} color={COLORS.TEXT_SECONDARY} />
              </TouchableOpacity>
            </View>

            <Text className="text-textSecondary text-xs leading-5">
              CarePilot HITL Scheduling: Reschedule requests are submitted to your doctor for approval before confirmation.
            </Text>

            <View>
              <Text className="text-textPrimary text-xs font-bold mb-1">New Desired Date</Text>
              <TextInput 
                className="border border-border rounded-xl p-3 bg-background text-textPrimary text-sm"
                value={newDate}
                onChangeText={setNewDate}
                placeholder="YYYY-MM-DD"
              />
            </View>

            <View>
              <Text className="text-textPrimary text-xs font-bold mb-1">Desired Time</Text>
              <TextInput 
                className="border border-border rounded-xl p-3 bg-background text-textPrimary text-sm"
                value={newTime}
                onChangeText={setNewTime}
                placeholder="e.g. 11:00 AM"
              />
            </View>

            <View>
              <Text className="text-textPrimary text-xs font-bold mb-1">Reason for Reschedule</Text>
              <TextInput 
                className="border border-border rounded-xl p-3 bg-background text-textPrimary text-sm h-20"
                value={reasonText}
                onChangeText={setReasonText}
                placeholder="Brief reason for rescheduling..."
                multiline
              />
            </View>

            <TouchableOpacity 
              onPress={handleSubmitReschedule}
              disabled={!reasonText.trim() || isSubmitting}
              className={`py-3.5 rounded-xl items-center justify-center mt-2 ${
                reasonText.trim() ? 'bg-primary' : 'bg-gray-300'
              }`}
            >
              {isSubmitting ? (
                <ActivityIndicator size="small" color="white" />
              ) : (
                <Text className="text-white font-bold text-sm">Submit Reschedule Request</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}
