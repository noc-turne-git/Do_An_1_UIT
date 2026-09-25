import { useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, TextInput, View } from 'react-native';
import { SymbolView } from 'expo-symbols';

import { ThemedText } from '@/components/themed-text';

type Props = {
  value: string;
  onChangeText: (value: string) => void;
  onSend?: () => void;
  placeholder?: string;
  accessibilityLabel?: string;
};

export function SharedChatInput({ value, onChangeText, onSend, placeholder = 'Ask anything else...', accessibilityLabel = 'Ask anything else' }: Props) {
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [attachment, setAttachment] = useState<string | null>(null);

  const nativeFileInput = Platform.OS === 'web'
    ? <input ref={fileInput} type="file" style={{ display: 'none' }} onChange={(event) => setAttachment(event.currentTarget.files?.[0]?.name ?? null)} />
    : null;

  return (
    <View style={styles.shell}>
      {nativeFileInput}
      {attachment ? <View style={styles.attachment}><ThemedText numberOfLines={1} style={styles.attachmentName}>{attachment}</ThemedText><Pressable accessibilityRole="button" accessibilityLabel="Remove attachment" onPress={() => { setAttachment(null); if (fileInput.current) fileInput.current.value = ''; }}><ThemedText style={styles.removeAttachment}>×</ThemedText></Pressable></View> : null}
      <View style={styles.row}>
        <Pressable accessibilityRole="button" accessibilityLabel="Attach a file" onPress={() => fileInput.current?.click()} style={styles.addButton}>
          <SymbolView name={{ ios: 'plus', android: 'add', web: 'add' }} tintColor="#111" size={21} />
        </Pressable>
        <TextInput value={value} onChangeText={onChangeText} onSubmitEditing={onSend} returnKeyType="send" placeholder={placeholder} placeholderTextColor="#858585" multiline={!onSend} style={styles.input} accessibilityLabel={accessibilityLabel} />
        <Pressable accessibilityRole="button" accessibilityLabel="Microphone" style={styles.micButton}>
          <SymbolView name={{ ios: 'mic', android: 'mic', web: 'mic' }} tintColor="#171717" size={21} />
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  shell: { width: '100%', minHeight: 108, marginTop: 12, paddingHorizontal: 18, paddingVertical: 12, borderWidth: 1, borderColor: '#d6d6d6', borderRadius: 25, backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 5, elevation: 2, justifyContent: 'center' },
  row: { minHeight: 40, flexDirection: 'row', alignItems: 'center', gap: 11 },
  input: { flex: 1, minHeight: 40, maxHeight: 120, paddingHorizontal: 2, paddingVertical: 7, color: '#171717', fontSize: 16, outlineStyle: 'none' as never },
  addButton: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: '#f2f2f2' },
  micButton: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  attachment: { flexDirection: 'row', alignSelf: 'flex-start', alignItems: 'center', gap: 8, maxWidth: '90%', marginBottom: 8, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14, backgroundColor: '#f2f3f4' },
  attachmentName: { maxWidth: 230, color: '#333', fontSize: 12 },
  removeAttachment: { color: '#555', fontSize: 18, lineHeight: 20 },
});
