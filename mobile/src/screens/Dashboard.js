import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Dimensions,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { theme } from '../utils/theme';
import { useStore } from '../store/useStore';
import ApiService from '../services/api';

const { width: screenWidth } = Dimensions.get('window');

export default function DashboardScreen({ navigation }) {
  const { user, apiKey, dashboardData, setDashboardData } = useStore();
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setIsLoading(true);
      
      // Parallel API calls for dashboard data
      const [stats, recentContacts, alerts, osintHistory] = await Promise.all([
        ApiService.getStats(apiKey),
        ApiService.getRecentContacts(apiKey, 5),
        ApiService.getAlerts(apiKey, { limit: 3, unread_only: true }),
        ApiService.getOSINTHistory(apiKey, 3),
      ]);

      setDashboardData({
        stats,
        recentContacts,
        alerts,
        osintHistory,
        lastUpdated: new Date(),
      });
    } catch (error) {
      console.error('Dashboard load error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadDashboardData();
    setRefreshing(false);
  };

  if (isLoading) {
    return <LoadingScreen />;
  }

  return (
    <LinearGradient
      colors={[theme.colors.background, theme.colors.backgroundVariant]}
      style={styles.container}
    >
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.contentContainer}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={theme.colors.primary}
            colors={[theme.colors.primary]}
          />
        }
      >
        {/* Header Section */}
        <View style={styles.header}>
          <View style={styles.headerContent}>
            <View>
              <Text style={styles.welcomeText}>INTELLIGENCE PLATFORM</Text>
              <Text style={styles.userText}>Welcome back, {user?.email?.split('@')[0]}</Text>
            </View>
            
            <TouchableOpacity style={styles.profileButton}>
              <View style={styles.statusIndicator} />
              <Ionicons name="person-circle-outline" size={32} color={theme.colors.primary} />
            </TouchableOpacity>
          </View>
          
          <Text style={styles.lastUpdated}>
            Last sync: {new Date(dashboardData?.lastUpdated).toLocaleTimeString()}
          </Text>
        </View>

        {/* Stats Grid */}
        <View style={styles.statsGrid}>
          <StatCard
            title="Total Contacts"
            value={dashboardData?.stats?.totalContacts || 0}
            icon="people"
            color={theme.colors.primary}
            subtitle="Active database"
          />
          
          <StatCard
            title="OSINT Queries"
            value={dashboardData?.stats?.osintQueries || 0}
            icon="search"
            color={theme.colors.secondary}
            subtitle="This month"
          />
          
          <StatCard
            title="Caller ID"
            value={dashboardData?.stats?.callerIdQueries || 0}
            icon="call"
            color={theme.colors.info}
            subtitle="Identifications"
          />
          
          <StatCard
            title="Threat Level"
            value={dashboardData?.stats?.threatLevel || "LOW"}
            icon="shield-checkmark"
            color={theme.colors.success}
            subtitle="Current status"
            isText={true}
          />
        </View>

        {/* Alerts Section */}
        {dashboardData?.alerts?.length > 0 && (
          <Section
            title="Security Alerts"
            icon="warning"
            iconColor={theme.colors.warning}
            onSeeAll={() => navigation.navigate('Alerts')}
          >
            {dashboardData.alerts.map((alert, index) => (
              <AlertCard
                key={alert.id || index}
                alert={alert}
                onPress={() => navigation.navigate('AlertDetail', { alertId: alert.id })}
              />
            ))}
          </Section>
        )}

        {/* Recent Contacts */}
        <Section
          title="Recent Intelligence"
          icon="document-text"
          iconColor={theme.colors.primary}
          onSeeAll={() => navigation.navigate('Contacts')}
        >
          {dashboardData?.recentContacts?.map((contact, index) => (
            <ContactCard
              key={contact.id || index}
              contact={contact}
              onPress={() => navigation.navigate('ContactDetail', { contactId: contact.id })}
            />
          ))}
        </Section>

        {/* OSINT Activity */}
        <Section
          title="OSINT Activity"
          icon="analytics"
          iconColor={theme.colors.secondary}
          onSeeAll={() => navigation.navigate('OSINT')}
        >
          {dashboardData?.osintHistory?.map((query, index) => (
            <OSINTCard
              key={query.id || index}
              query={query}
              onPress={() => navigation.navigate('OSINTDetail', { queryId: query.id })}
            />
          ))}
        </Section>

        {/* Quick Actions */}
        <Section title="Quick Actions" icon="flash" iconColor={theme.colors.primary}>
          <View style={styles.actionsGrid}>
            <ActionButton
              title="Enrich Contact"
              icon="person-add"
              onPress={() => navigation.navigate('Contacts', { action: 'enrich' })}
            />
            
            <ActionButton
              title="OSINT Lookup"
              icon="search-circle"
              onPress={() => navigation.navigate('OSINT', { action: 'new' })}
            />
            
            <ActionButton
              title="Scan QR"
              icon="qr-code-outline"
              onPress={() => navigation.navigate('QRCard', { action: 'scan' })}
            />
            
            <ActionButton
              title="Monitor"
              icon="eye"
              onPress={() => navigation.navigate('Monitoring')}
            />
          </View>
        </Section>

        <View style={styles.bottomPadding} />
      </ScrollView>
    </LinearGradient>
  );
}

// Loading Screen
const LoadingScreen = () => (
  <LinearGradient
    colors={[theme.colors.background, theme.colors.backgroundVariant]}
    style={styles.loadingContainer}
  >
    <ActivityIndicator size="large" color={theme.colors.primary} />
    <Text style={styles.loadingText}>Loading intelligence data...</Text>
  </LinearGradient>
);

// Stat Card Component
const StatCard = ({ title, value, icon, color, subtitle, isText }) => (
  <LinearGradient
    colors={[theme.colors.surface, theme.colors.surfaceVariant]}
    style={styles.statCard}
  >
    <View style={styles.statHeader}>
      <Ionicons name={icon} size={20} color={color} />
      <Text style={styles.statTitle}>{title}</Text>
    </View>
    
    <Text style={[styles.statValue, { color }, isText && styles.statValueText]}>
      {isText ? value : value.toLocaleString()}
    </Text>
    
    <Text style={styles.statSubtitle}>{subtitle}</Text>
    
    {/* Glow effect for active stats */}
    <View style={[styles.statGlow, { backgroundColor: color }]} />
  </LinearGradient>
);

// Section Component
const Section = ({ title, icon, iconColor, children, onSeeAll }) => (
  <View style={styles.section}>
    <View style={styles.sectionHeader}>
      <View style={styles.sectionTitleContainer}>
        <Ionicons name={icon} size={18} color={iconColor} />
        <Text style={styles.sectionTitle}>{title}</Text>
      </View>
      
      {onSeeAll && (
        <TouchableOpacity onPress={onSeeAll} style={styles.seeAllButton}>
          <Text style={styles.seeAllText}>View All</Text>
          <Ionicons name="chevron-forward" size={14} color={theme.colors.primary} />
        </TouchableOpacity>
      )}
    </View>
    
    <View style={styles.sectionContent}>
      {children}
    </View>
  </View>
);

// Alert Card Component
const AlertCard = ({ alert, onPress }) => (
  <TouchableOpacity style={styles.alertCard} onPress={onPress}>
    <View style={styles.alertIndicator} />
    
    <View style={styles.alertContent}>
      <Text style={styles.alertTitle}>{alert.title}</Text>
      <Text style={styles.alertMessage} numberOfLines={2}>
        {alert.message}
      </Text>
      <Text style={styles.alertTime}>
        {new Date(alert.created_at).toLocaleTimeString()}
      </Text>
    </View>
    
    <Ionicons name="chevron-forward" size={16} color={theme.colors.textTertiary} />
  </TouchableOpacity>
);

// Contact Card Component
const ContactCard = ({ contact, onPress }) => (
  <TouchableOpacity style={styles.contactCard} onPress={onPress}>
    <View style={styles.contactAvatar}>
      <Text style={styles.contactInitial}>
        {contact.name?.charAt(0) || contact.email?.charAt(0) || '?'}
      </Text>
    </View>
    
    <View style={styles.contactInfo}>
      <Text style={styles.contactName}>
        {contact.name || 'Unknown Contact'}
      </Text>
      <Text style={styles.contactEmail} numberOfLines={1}>
        {contact.email}
      </Text>
      <Text style={styles.contactCompany} numberOfLines={1}>
        {contact.company || 'No company'}
      </Text>
    </View>
    
    <View style={styles.contactMeta}>
      <Text style={styles.contactSource}>{contact.source?.toUpperCase()}</Text>
      <Ionicons name="chevron-forward" size={16} color={theme.colors.textTertiary} />
    </View>
  </TouchableOpacity>
);

// OSINT Card Component
const OSINTCard = ({ query, onPress }) => (
  <TouchableOpacity style={styles.osintCard} onPress={onPress}>
    <View style={styles.osintHeader}>
      <Ionicons 
        name={query.type === 'email' ? 'mail' : query.type === 'phone' ? 'call' : 'person'} 
        size={16} 
        color={theme.colors.secondary} 
      />
      <Text style={styles.osintType}>{query.type?.toUpperCase()}</Text>
      <View style={styles.osintStatus}>
        <Text style={styles.osintStatusText}>
          {query.status || 'COMPLETED'}
        </Text>
      </View>
    </View>
    
    <Text style={styles.osintQuery} numberOfLines={1}>
      {query.query}
    </Text>
    
    <Text style={styles.osintTime}>
      {new Date(query.created_at).toLocaleString()}
    </Text>
  </TouchableOpacity>
);

// Action Button Component
const ActionButton = ({ title, icon, onPress }) => (
  <TouchableOpacity style={styles.actionButton} onPress={onPress}>
    <LinearGradient
      colors={[theme.colors.surface, theme.colors.surfaceVariant]}
      style={styles.actionButtonGradient}
    >
      <Ionicons name={icon} size={24} color={theme.colors.primary} />
      <Text style={styles.actionButtonText}>{title}</Text>
    </LinearGradient>
  </TouchableOpacity>
);

// Styles
const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  
  scrollView: {
    flex: 1,
  },
  
  contentContainer: {
    paddingBottom: 100,
  },
  
  // Header Styles
  header: {
    padding: theme.spacing.lg,
    paddingTop: 60, // Account for status bar
  },
  
  headerContent: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: theme.spacing.sm,
  },
  
  welcomeText: {
    fontFamily: theme.fonts.mono.regular,
    fontSize: theme.fonts.sizes.small,
    color: theme.colors.primary,
    letterSpacing: 1,
    marginBottom: 4,
  },
  
  userText: {
    fontFamily: theme.fonts.bold,
    fontSize: theme.fonts.sizes.heading,
    color: theme.colors.text,
  },
  
  profileButton: {
    position: 'relative',
    alignItems: 'center',
  },
  
  statusIndicator: {
    position: 'absolute',
    top: 2,
    right: 2,
    width: 8,
    height: 8,
    backgroundColor: theme.colors.success,
    borderRadius: 4,
    zIndex: 1,
    ...theme.shadows.glow,
  },
  
  lastUpdated: {
    fontFamily: theme.fonts.mono.regular,
    fontSize: theme.fonts.sizes.tiny,
    color: theme.colors.textTertiary,
  },
  
  // Stats Grid
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: theme.spacing.lg,
    marginBottom: theme.spacing.lg,
    gap: theme.spacing.md,
  },
  
  statCard: {
    width: (screenWidth - theme.spacing.lg * 2 - theme.spacing.md) / 2,
    padding: theme.spacing.md,
    borderRadius: theme.borderRadius.lg,
    borderWidth: 1,
    borderColor: theme.colors.border,
    position: 'relative',
    overflow: 'hidden',
  },
  
  statHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  
  statTitle: {
    fontFamily: theme.fonts.regular,
    fontSize: theme.fonts.sizes.small,
    color: theme.colors.textSecondary,
    marginLeft: theme.spacing.xs,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  
  statValue: {
    fontFamily: theme.fonts.mono.bold,
    fontSize: theme.fonts.sizes.title,
    marginBottom: theme.spacing.xs,
  },
  
  statValueText: {
    fontSize: theme.fonts.sizes.body,
  },
  
  statSubtitle: {
    fontFamily: theme.fonts.regular,
    fontSize: theme.fonts.sizes.tiny,
    color: theme.colors.textTertiary,
  },
  
  statGlow: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: 2,
    opacity: 0.3,
  },
  
  // Section Styles
  section: {
    marginBottom: theme.spacing.xl,
  },
  
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: theme.spacing.lg,
    marginBottom: theme.spacing.md,
  },
  
  sectionTitleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  
  sectionTitle: {
    fontFamily: theme.fonts.bold,
    fontSize: theme.fonts.sizes.subtitle,
    color: theme.colors.text,
    marginLeft: theme.spacing.sm,
  },
  
  seeAllButton: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  
  seeAllText: {
    fontFamily: theme.fonts.medium,
    fontSize: theme.fonts.sizes.small,
    color: theme.colors.primary,
    marginRight: theme.spacing.xs,
  },
  
  sectionContent: {
    paddingHorizontal: theme.spacing.lg,
  },
  
  // Alert Card
  alertCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  
  alertIndicator: {
    width: 4,
    height: '100%',
    backgroundColor: theme.colors.warning,
    borderRadius: 2,
    marginRight: theme.spacing.md,
  },
  
  alertContent: {
    flex: 1,
  },
  
  alertTitle: {
    fontFamily: theme.fonts.medium,
    fontSize: theme.fonts.sizes.body,
    color: theme.colors.text,
    marginBottom: 2,
  },
  
  alertMessage: {
    fontFamily: theme.fonts.regular,
    fontSize: theme.fonts.sizes.small,
    color: theme.colors.textSecondary,
    marginBottom: 4,
  },
  
  alertTime: {
    fontFamily: theme.fonts.mono.regular,
    fontSize: theme.fonts.sizes.tiny,
    color: theme.colors.textTertiary,
  },
  
  // Contact Card
  contactCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  
  contactAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: theme.colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: theme.spacing.md,
  },
  
  contactInitial: {
    fontFamily: theme.fonts.bold,
    fontSize: theme.fonts.sizes.subtitle,
    color: theme.colors.textOnPrimary,
  },
  
  contactInfo: {
    flex: 1,
  },
  
  contactName: {
    fontFamily: theme.fonts.medium,
    fontSize: theme.fonts.sizes.body,
    color: theme.colors.text,
    marginBottom: 2,
  },
  
  contactEmail: {
    fontFamily: theme.fonts.mono.regular,
    fontSize: theme.fonts.sizes.small,
    color: theme.colors.textSecondary,
    marginBottom: 2,
  },
  
  contactCompany: {
    fontFamily: theme.fonts.regular,
    fontSize: theme.fonts.sizes.tiny,
    color: theme.colors.textTertiary,
  },
  
  contactMeta: {
    alignItems: 'flex-end',
  },
  
  contactSource: {
    fontFamily: theme.fonts.mono.regular,
    fontSize: theme.fonts.sizes.tiny,
    color: theme.colors.primary,
    marginBottom: theme.spacing.xs,
  },
  
  // OSINT Card
  osintCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  
  osintHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  
  osintType: {
    fontFamily: theme.fonts.mono.bold,
    fontSize: theme.fonts.sizes.tiny,
    color: theme.colors.secondary,
    marginLeft: theme.spacing.xs,
    marginRight: theme.spacing.sm,
  },
  
  osintStatus: {
    backgroundColor: theme.colors.success,
    paddingHorizontal: theme.spacing.xs,
    paddingVertical: 2,
    borderRadius: theme.borderRadius.sm,
    marginLeft: 'auto',
  },
  
  osintStatusText: {
    fontFamily: theme.fonts.mono.regular,
    fontSize: theme.fonts.sizes.tiny,
    color: theme.colors.textOnPrimary,
  },
  
  osintQuery: {
    fontFamily: theme.fonts.mono.regular,
    fontSize: theme.fonts.sizes.body,
    color: theme.colors.text,
    marginBottom: theme.spacing.xs,
  },
  
  osintTime: {
    fontFamily: theme.fonts.mono.regular,
    fontSize: theme.fonts.sizes.tiny,
    color: theme.colors.textTertiary,
  },
  
  // Actions Grid
  actionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.md,
  },
  
  actionButton: {
    width: (screenWidth - theme.spacing.lg * 2 - theme.spacing.md) / 2,
  },
  
  actionButtonGradient: {
    padding: theme.spacing.md,
    borderRadius: theme.borderRadius.lg,
    borderWidth: 1,
    borderColor: theme.colors.border,
    alignItems: 'center',
  },
  
  actionButtonText: {
    fontFamily: theme.fonts.medium,
    fontSize: theme.fonts.sizes.small,
    color: theme.colors.text,
    marginTop: theme.spacing.xs,
    textAlign: 'center',
  },
  
  // Loading
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  
  loadingText: {
    fontFamily: theme.fonts.mono.regular,
    fontSize: theme.fonts.sizes.small,
    color: theme.colors.textSecondary,
    marginTop: theme.spacing.md,
  },
  
  bottomPadding: {
    height: theme.spacing.xl,
  },
});
