import { View, Text, ScrollView, TextInput, TouchableOpacity, KeyboardAvoidingView, Platform, ActivityIndicator } from 'react-native';
import { useState, useEffect, useRef } from 'react';
import { useAuthStore } from '../../../store/authStore';
import { useMockWorkflow } from '../../../services/mock/mockWorkflow';
import { consultationApi } from '../../../services/api/consultationApi';
import { useRouter } from 'expo-router';
import { Feather } from '@expo/vector-icons';
import { COLORS } from '../../../constants/colors';

const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English', flag: '🇺🇸' },
  { code: 'ta', label: 'Tamil', flag: '🇮🇳' },
  { code: 'es', label: 'Spanish', flag: '🇪🇸' },
  { code: 'fr', label: 'French', flag: '🇫🇷' },
  { code: 'de', label: 'German', flag: '🇩🇪' },
];

export default function ChatScreen() {
  const [query, setQuery] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [selectedLanguage, setSelectedLanguage] = useState('en');
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const user = useAuthStore(s => s.user);
  const submitConsultation = useMockWorkflow(s => s.submitConsultation);
  const router = useRouter();

  // Web Audio API for speech recording (web platform)
  useEffect(() => {
    if (Platform.OS !== 'web') return;

    if (isRecording && !mediaRecorderRef.current) {
      audioChunksRef.current = [];
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then(stream => {
          const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
          mediaRecorderRef.current = recorder;

          recorder.ondataavailable = (e: BlobEvent) => {
            if (e.data.size > 0) audioChunksRef.current.push(e.data);
          };

          recorder.onstop = () => {
            stream.getTracks().forEach(t => t.stop());
            const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
            const file = new File([blob], 'recording.webm', { type: 'audio/webm' });
            handleTranscribeFile(file);
          };

          recorder.start(100);
        })
        .catch(err => {
          console.error('Microphone access denied:', err);
          setIsRecording(false);
          alert('Microphone access is required for voice input.');
        });
    }

    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
    };
  }, [isRecording]);

  const handleTranscribeFile = async (file: File) => {
    setIsRecording(false);
    setIsSubmitting(true);
    try {
      const res = await consultationApi.transcribeAudio(file);
      const transcribedText = res.text;
      setQuery(transcribedText);
    } catch (err: any) {
      console.warn('STT failed:', err);
      alert('Speech-to-text failed. Please type your query instead.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSpeak = async (text: string) => {
    setIsSpeaking(true);
    try {
      const url = await consultationApi.synthesizeAudio(text, 'en-US-JennyNeural');
      setAudioUrl(url);
    } catch (err: any) {
      console.warn('TTS failed:', err);
      alert('Text-to-speech failed.');
    } finally {
      setIsSpeaking(false);
    }
  };

  const handleSend = async () => {
    const textToSend = query.trim();
    if (!textToSend || !user || isSubmitting) return;
    setIsSubmitting(true);

    let consultationId: string | null = null;
    try {
      const res = await consultationApi.submitConsultation(user.id, textToSend, selectedLanguage);
      if (res && res.consultation_id) {
        consultationId = res.consultation_id;
        // Auto-play the doctor response via TTS when delivered
      }
    } catch (err) {
      console.warn('Backend consult API call failed, falling back to local workflow:', err);
    }

    const localId = await submitConsultation(query.trim(), user.id, `${user.firstName} ${user.lastName}`);
    const targetId = consultationId || localId;
    setQuery('');
    setIsSubmitting(false);
    router.push(`/(tabs)/chat/${targetId}` as any);
  };

  const toggleRecording = () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
    } else {
      setIsRecording(true);
    }
  };

  return (
    <KeyboardAvoidingView 
      className="flex-1 bg-background" 
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      <ScrollView className="flex-1 p-4">
        <View className="bg-card p-4 rounded-xl border border-border mb-4">
          <View className="flex-row items-center justify-between mb-2">
            <Text className="text-textPrimary font-semibold">CarePilot AI Assistant</Text>
            <View className="flex-row items-center space-x-2">
              <Text className="text-[10px] text-textSecondary font-bold uppercase">{selectedLanguage.toUpperCase()}</Text>
              <TouchableOpacity onPress={() => setSelectedLanguage(l => (l === 'en' ? 'ta' : 'en'))}>
                <Feather name="globe" size={16} color={COLORS.PRIMARY} />
              </TouchableOpacity>
            </View>
          </View>
          <Text className="text-textSecondary">Describe your symptoms or ask a question about your health. I will analyze it and prepare a report for your doctor.</Text>
        </View>
      </ScrollView>
      
      <View className="p-4 bg-card border-t border-border flex-row items-end">
        <TextInput
          className="flex-1 border border-border rounded-xl p-3 max-h-32 text-textPrimary bg-background mr-2"
          placeholder={selectedLanguage === 'ta' ? 'உங்கள் சுகாதாரக் கேள்வியைக் கேட்கவும்...' : 'Describe your issue...'}
          value={query}
          onChangeText={setQuery}
          multiline
        />
        {/* Voice Record Button */}
        <TouchableOpacity 
          className={`h-12 w-12 rounded-full items-center justify-center mr-2 ${
            isRecording ? 'bg-urgent animate-pulse' : 'bg-secondary'
          }`}
          onPress={toggleRecording}
          disabled={isSubmitting}
        >
          {isRecording ? (
            <Feather name="mic-off" size={20} color="white" />
          ) : (
            <Feather name="mic" size={20} color="white" />
          )}
        </TouchableOpacity>
        <TouchableOpacity 
          className="h-12 w-12 rounded-xl items-center justify-center bg-primary"
          onPress={handleSend}
          disabled={!query.trim() || isSubmitting}
        >
          {isSubmitting ? (
            <ActivityIndicator size="small" color="white" />
          ) : (
            <Feather name="send" size={20} color="white" />
          )}
        </TouchableOpacity>
      </View>
      
      {/* Audio Playback Bar */}
      {audioUrl && (
        <View className="p-4 bg-success/10 border border-success/30 rounded-xl flex-row items-center mb-4">
          <Feather name="volume-2" size={18} color={COLORS.SUCCESS} className="mr-3" />
          <View className="flex-1">
            <Text className="text-textPrimary font-medium text-sm">Doctor response audio ready</Text>
            <Text className="text-textSecondary text-xs">Tap to play spoken response</Text>
          </View>
          <TouchableOpacity 
            className="bg-success p-2 rounded-lg"
            onPress={() => {
              if (audioUrl) {
                const audio = new Audio(audioUrl);
                audio.play();
                setIsSpeaking(true);
                audio.onended = () => setIsSpeaking(false);
              }
            }}
          >
            <Feather name="play" size={20} color="white" />
          </TouchableOpacity>
        </View>
      )}
    </KeyboardAvoidingView>
  );
}