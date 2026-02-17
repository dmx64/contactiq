import React, { useEffect, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'expo-status-bar';
import { View, Text, StyleSheet, Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { LinearGradient } from 'expo-linear-gradient';
import * as Font from 'expo-font';
import { Ionicons } from '@expo/vector-icons';

// Import screens
import DashboardScreen from './src/screens/Dashboard';
import ContactsScreen from './src/screens/Contacts';
import CallerIDScreen from './src/screens/CallerID';
import OSINTScreen from './src/screens/OSINT';
import QRCardScreen from './src/screens/QRCard';
import SettingsScreen from './src/screens/Settings';

// Import store
import { useStore } from './src/store/useStore';
import AuthService from './src/services/auth';

// Import theme
import { theme, fonts } from './src/utils/theme';

const Tab = createBottomTabNavigator();

export default function App() {
  const [isReady, setIsReady] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const { user, setUser, setApiKey } = useStore();

  useEffect(() => {
    loadFonts();
  }, []);

  const loadFonts = async () => {
    try {
      await Font.loadAsync({
        'JetBrainsMono-Regular': require('./assets/fonts/JetBrainsMono-Regular.ttf'),
        'JetBrainsMono-Bold': require('./assets/fonts/JetBrainsMono-Bold.ttf'),
        'Inter-Regular': require('./assets/fonts/Inter-Regular.ttf'),
        'Inter-Medium': require('./assets/fonts/Inter-Medium.ttf'),
        'Inter-Bold': require('./assets/fonts/Inter-Bold.ttf'),
      });
      
      await checkAuthStatus();
      setIsReady(true);
    } catch (error) {
      console.error('Error loading fonts:', error);
      setIsReady(true);
    }
  };

  const checkAuthStatus = async () => {
    try {
      const token = await SecureStore.getItemAsync('access_token');
      const apiKey = await SecureStore.getItemAsync('api_key');
      
      if (token && apiKey) {
        // Verify token with backend
        const isValid = await AuthService.verifyToken(token);
        
        if (isValid) {
          setApiKey(apiKey);
          setIsAuthenticated(true);
          
          // Load user profile
          const profile = await AuthService.getProfile(apiKey);
          setUser(profile);
        } else {
          // Clear invalid tokens
          await SecureStore.deleteItemAsync('access_token');
          await SecureStore.deleteItemAsync('api_key');
        }
      }
    } catch (error) {
      console.error('Auth check failed:', error);
    }
  };

  if (!isReady) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <AuthScreen onAuthSuccess={checkAuthStatus} />;
  }

  return (
    <NavigationContainer theme={theme.navigation}>
      <StatusBar style="light" backgroundColor={theme.colors.background} />
      
      <Tab.Navigator
        screenOptions={({ route }) => ({
          headerShown: false,
          tabBarActiveTintColor: theme.colors.primary,
          tabBarInactiveTintColor: theme.colors.textSecondary,
          tabBarStyle: styles.tabBar,
          tabBarLabelStyle: styles.tabBarLabel,
          tabBarBackground: () => (
            <LinearGradient
              colors={[theme.colors.surface, theme.colors.surfaceVariant]}
              style={{ flex: 1 }}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
            />
          ),
          tabBarIcon: ({ focused, color, size }) => {
            let iconName;
            
            switch (route.name) {
              case 'Dashboard':
                iconName = focused ? 'grid' : 'grid-outline';
                break;
              case 'Contacts':
                iconName = focused ? 'people' : 'people-outline';
                break;
              case 'Caller ID':
                iconName = focused ? 'call' : 'call-outline';
                break;
              case 'OSINT':
                iconName = focused ? 'search' : 'search-outline';
                break;
              case 'QR Card':
                iconName = focused ? 'qr-code' : 'qr-code-outline';
                break;
              case 'Settings':
                iconName = focused ? 'settings' : 'settings-outline';
                break;
            }

            return (
              <View style={[styles.tabIcon, focused && styles.tabIconFocused]}>
                <Ionicons name={iconName} size={size} color={color} />
                {focused && <View style={styles.tabIndicator} />}
              </View>
            );
          },
        })}
      >
        <Tab.Screen 
          name="Dashboard" 
          component={DashboardScreen}
          options={{
            tabBarLabel: 'Dashboard',
            tabBarBadge: user?.alerts?.unread > 0 ? user.alerts.unread : null,
          }}
        />
        
        <Tab.Screen 
          name="Contacts" 
          component={ContactsScreen}
          options={{
            tabBarLabel: 'Contacts',
            tabBarBadge: user?.stats?.newContacts > 0 ? user.stats.newContacts : null,
          }}
        />
        
        <Tab.Screen 
          name="Caller ID" 
          component={CallerIDScreen}
          options={{ tabBarLabel: 'Caller ID' }}
        />
        
        <Tab.Screen 
          name="OSINT" 
          component={OSINTScreen}
          options={{ tabBarLabel: 'OSINT' }}
        />
        
        <Tab.Screen 
          name="QR Card" 
          component={QRCardScreen}
          options={{ tabBarLabel: 'QR Card' }}
        />
        
        <Tab.Screen 
          name="Settings" 
          component={SettingsScreen}
          options={{ tabBarLabel: 'Settings' }}
        />
      </Tab.Navigator>
    </NavigationContainer>
  );
}

// Loading Screen Component
const LoadingScreen = () => (
  <LinearGradient
    colors={[theme.colors.background, theme.colors.backgroundVariant]}
    style={styles.loadingContainer}
  >
    <View style={styles.loadingContent}>
      <Text style={styles.loadingTitle}>ContactIQ</Text>
      <Text style={styles.loadingSubtitle}>Intelligence Platform</Text>
      
      <View style={styles.loadingBar}>
        <View style={styles.loadingProgress} />
      </View>
      
      <Text style={styles.loadingText}>Initializing secure environment...</Text>
    </View>
  </LinearGradient>
);

// Auth Screen Component (simplified - full version in separate file)
const AuthScreen = ({ onAuthSuccess }) => (
  <LinearGradient
    colors={[theme.colors.background, theme.colors.backgroundVariant]}
    style={styles.authContainer}
  >
    <View style={styles.authContent}>
      <Text style={styles.authTitle}>ContactIQ</Text>
      <Text style={styles.authSubtitle}>Contact Intelligence Platform</Text>
      <Text style={styles.authDescription}>
        Secure access required for intelligence operations
      </Text>
      
      {/* Auth form would be here */}
      <Text style={styles.authNote}>
        Authentication interface will be implemented in AuthScreen component
      </Text>
    </View>
  </LinearGradient>
);

const styles = StyleSheet.create({
  // Tab Bar Styling
  tabBar: {
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    height: Platform.OS === 'ios' ? 88 : 68,
    paddingBottom: Platform.OS === 'ios' ? 24 : 8,
    paddingTop: 8,
    elevation: 0,
    shadowOpacity: 0,
  },
  
  tabBarLabel: {
    fontFamily: fonts.regular,
    fontSize: 11,
    fontWeight: '500',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  
  tabIcon: {
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  
  tabIconFocused: {
    transform: [{ scale: 1.1 }],
  },
  
  tabIndicator: {
    position: 'absolute',
    bottom: -4,
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: theme.colors.primary,
  },
  
  // Loading Screen Styling
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  
  loadingContent: {
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  
  loadingTitle: {
    fontFamily: fonts.mono.bold,
    fontSize: 32,
    color: theme.colors.primary,
    marginBottom: 8,
    letterSpacing: 2,
  },
  
  loadingSubtitle: {
    fontFamily: fonts.regular,
    fontSize: 16,
    color: theme.colors.textSecondary,
    marginBottom: 48,
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  
  loadingBar: {
    width: 200,
    height: 2,
    backgroundColor: theme.colors.surfaceVariant,
    borderRadius: 1,
    marginBottom: 24,
    overflow: 'hidden',
  },
  
  loadingProgress: {
    height: '100%',
    width: '100%',
    backgroundColor: theme.colors.primary,
    borderRadius: 1,
    // Animation would be added here
  },
  
  loadingText: {
    fontFamily: fonts.mono.regular,
    fontSize: 12,
    color: theme.colors.textTertiary,
    letterSpacing: 0.5,
  },
  
  // Auth Screen Styling
  authContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  
  authContent: {
    alignItems: 'center',
    paddingHorizontal: 32,
    width: '100%',
    maxWidth: 400,
  },
  
  authTitle: {
    fontFamily: fonts.mono.bold,
    fontSize: 40,
    color: theme.colors.primary,
    marginBottom: 8,
    letterSpacing: 3,
  },
  
  authSubtitle: {
    fontFamily: fonts.regular,
    fontSize: 18,
    color: theme.colors.textSecondary,
    marginBottom: 16,
    letterSpacing: 1,
  },
  
  authDescription: {
    fontFamily: fonts.regular,
    fontSize: 14,
    color: theme.colors.textTertiary,
    textAlign: 'center',
    marginBottom: 32,
    lineHeight: 20,
  },
  
  authNote: {
    fontFamily: fonts.mono.regular,
    fontSize: 12,
    color: theme.colors.textTertiary,
    textAlign: 'center',
    padding: 16,
    backgroundColor: theme.colors.surface,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: theme.colors.border,
    marginTop: 32,
  },
});
