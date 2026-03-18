import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';
import {
  fetchUserProfile,
  fetchWallPosts,
  createWallPost,
  updateWallPost as updateWallPostApi,
  deleteWallPost as deleteWallPostApi,
  fetchFriends,
  fetchIncomingRequests,
  fetchOutgoingRequests,
  sendFriendRequest,
  acceptFriendRequest,
  rejectFriendRequest,
  removeFriend,
  uploadUserAvatar,
  updateProfileSettings as updateProfileSettingsApi,
  updateUsername as updateUsernameApi,
  fetchUserCharacters,
  uploadProfileBackground as uploadProfileBackgroundApi,
  deleteProfileBackground as deleteProfileBackgroundApi,
} from '../../api/userProfile';
import { getMe } from './userSlice';
import type { RootState } from '../store';

// ── Types ──

export interface WallPost {
  id: number;
  author_id: number;
  author_username: string;
  author_avatar: string | null;
  wall_owner_id: number;
  content: string;
  created_at: string;
}

export interface Friend {
  id: number;
  username: string;
  avatar: string | null;
}

export interface FriendRequest {
  id: number;
  user: Friend;
  created_at: string;
}

interface PostStats {
  total_posts: number;
  last_post_date: string | null;
}

interface CharacterShort {
  id: number;
  name: string;
  avatar: string;
  level: number | null;
}

export interface UserProfile {
  id: number;
  username: string;
  avatar: string | null;
  registered_at: string | null;
  character: CharacterShort | null;
  post_stats: PostStats;
  is_friend: boolean | null;
  friendship_status: string | null;
  friendship_id: number | null;
  profile_bg_color?: string | null;
  profile_bg_image?: string | null;
  nickname_color?: string | null;
  avatar_frame?: string | null;
  avatar_effect_color?: string | null;
  status_text?: string | null;
  profile_bg_position?: string | null;
}

export interface UserCharacterItem {
  id: number;
  name: string;
  avatar: string | null;
  level: number | null;
  rp_posts_count: number;
  last_rp_post_date: string | null;
}

interface UserProfileState {
  profile: UserProfile | null;
  posts: WallPost[];
  postsPage: number;
  hasMorePosts: boolean;
  friends: Friend[];
  incomingRequests: FriendRequest[];
  outgoingRequests: FriendRequest[];
  characters: UserCharacterItem[];
  loading: boolean;
  postsLoading: boolean;
  friendsLoading: boolean;
  avatarUploading: boolean;
  charactersLoading: boolean;
  settingsUpdating: boolean;
  error: string | null;
}

const initialState: UserProfileState = {
  profile: null,
  posts: [],
  postsPage: 1,
  hasMorePosts: true,
  friends: [],
  incomingRequests: [],
  outgoingRequests: [],
  characters: [],
  loading: false,
  postsLoading: false,
  friendsLoading: false,
  avatarUploading: false,
  charactersLoading: false,
  settingsUpdating: false,
  error: null,
};

// ── Thunks ──

export const loadUserProfile = createAsyncThunk(
  'userProfile/loadProfile',
  async (userId: number) => {
    const { data } = await fetchUserProfile(userId);
    return data as UserProfile;
  },
);

export const loadWallPosts = createAsyncThunk(
  'userProfile/loadWallPosts',
  async ({ userId, page }: { userId: number; page: number }) => {
    const { data } = await fetchWallPosts(userId, page);
    return { posts: data as WallPost[], page };
  },
);

export const createPost = createAsyncThunk(
  'userProfile/createPost',
  async ({ userId, content }: { userId: number; content: string }) => {
    const { data } = await createWallPost(userId, content);
    return data as WallPost;
  },
);

export const editPost = createAsyncThunk(
  'userProfile/editPost',
  async ({ postId, content }: { postId: number; content: string }) => {
    const { data } = await updateWallPostApi(postId, content);
    return data as WallPost;
  },
);

export const deletePost = createAsyncThunk(
  'userProfile/deletePost',
  async (postId: number) => {
    await deleteWallPostApi(postId);
    return postId;
  },
);

export const loadFriends = createAsyncThunk(
  'userProfile/loadFriends',
  async (userId: number) => {
    const { data } = await fetchFriends(userId);
    return data as Friend[];
  },
);

export const loadIncomingRequests = createAsyncThunk(
  'userProfile/loadIncomingRequests',
  async () => {
    const { data } = await fetchIncomingRequests();
    return data as FriendRequest[];
  },
);

export const loadOutgoingRequests = createAsyncThunk(
  'userProfile/loadOutgoingRequests',
  async () => {
    const { data } = await fetchOutgoingRequests();
    return data as FriendRequest[];
  },
);

export const sendRequest = createAsyncThunk(
  'userProfile/sendRequest',
  async (friendId: number) => {
    const { data } = await sendFriendRequest(friendId);
    return data;
  },
);

export const acceptRequest = createAsyncThunk(
  'userProfile/acceptRequest',
  async ({ friendshipId, userId }: { friendshipId: number; userId: number }, { dispatch }) => {
    await acceptFriendRequest(friendshipId);
    dispatch(loadFriends(userId));
    dispatch(loadIncomingRequests());
    return friendshipId;
  },
);

export const rejectRequest = createAsyncThunk(
  'userProfile/rejectRequest',
  async (friendshipId: number) => {
    await rejectFriendRequest(friendshipId);
    return friendshipId;
  },
);

export const removeFriendThunk = createAsyncThunk(
  'userProfile/removeFriend',
  async ({ friendId, userId }: { friendId: number; userId: number }, { dispatch }) => {
    await removeFriend(friendId);
    dispatch(loadFriends(userId));
    return friendId;
  },
);

export const uploadAvatar = createAsyncThunk(
  'userProfile/uploadAvatar',
  async ({ userId, file }: { userId: number; file: File }, { dispatch }) => {
    const { data } = await uploadUserAvatar(userId, file);
    dispatch(getMe());
    return data.avatar_url as string;
  },
);

export const updateProfileSettings = createAsyncThunk(
  'userProfile/updateProfileSettings',
  async (
    {
      userId,
      settings,
    }: {
      userId: number;
      settings: {
        profile_bg_color?: string | null;
        nickname_color?: string | null;
        avatar_frame?: string | null;
        avatar_effect_color?: string | null;
        status_text?: string | null;
        profile_bg_position?: string | null;
      };
    },
    { dispatch, rejectWithValue },
  ) => {
    try {
      const { data } = await updateProfileSettingsApi(settings);
      dispatch(loadUserProfile(userId));
      return data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      return rejectWithValue(
        error.response?.data?.detail ?? 'Не удалось сохранить настройки',
      );
    }
  },
);

export const updateUsername = createAsyncThunk(
  'userProfile/updateUsername',
  async (
    { userId, username }: { userId: number; username: string },
    { dispatch, rejectWithValue },
  ) => {
    try {
      const { data } = await updateUsernameApi(username);
      dispatch(getMe());
      dispatch(loadUserProfile(userId));
      return data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      return rejectWithValue(
        error.response?.data?.detail ?? 'Не удалось изменить никнейм',
      );
    }
  },
);

export const loadUserCharacters = createAsyncThunk(
  'userProfile/loadUserCharacters',
  async (userId: number) => {
    const { data } = await fetchUserCharacters(userId);
    return data.characters as UserCharacterItem[];
  },
);

export const uploadProfileBackground = createAsyncThunk(
  'userProfile/uploadProfileBackground',
  async (
    { userId, file }: { userId: number; file: File },
    { dispatch, rejectWithValue },
  ) => {
    try {
      const { data } = await uploadProfileBackgroundApi(userId, file);
      dispatch(loadUserProfile(userId));
      return data.profile_bg_image as string;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      return rejectWithValue(
        error.response?.data?.detail ?? 'Не удалось загрузить фон профиля',
      );
    }
  },
);

export const deleteProfileBackground = createAsyncThunk(
  'userProfile/deleteProfileBackground',
  async (userId: number, { dispatch, rejectWithValue }) => {
    try {
      await deleteProfileBackgroundApi(userId);
      dispatch(loadUserProfile(userId));
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      return rejectWithValue(
        error.response?.data?.detail ?? 'Не удалось удалить фон профиля',
      );
    }
  },
);

// ── Slice ──

const userProfileSlice = createSlice({
  name: 'userProfile',
  initialState,
  reducers: {
    resetUserProfile(state) {
      Object.assign(state, initialState);
    },
  },
  extraReducers: (builder) => {
    builder
      // Profile
      .addCase(loadUserProfile.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loadUserProfile.fulfilled, (state, action) => {
        state.loading = false;
        state.profile = action.payload;
      })
      .addCase(loadUserProfile.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message ?? 'Ошибка загрузки профиля';
      })

      // Wall posts
      .addCase(loadWallPosts.pending, (state) => {
        state.postsLoading = true;
      })
      .addCase(loadWallPosts.fulfilled, (state, action) => {
        state.postsLoading = false;
        const { posts, page } = action.payload;
        if (page === 1) {
          state.posts = posts;
        } else {
          state.posts = [...state.posts, ...posts];
        }
        state.postsPage = page;
        state.hasMorePosts = posts.length >= 20;
      })
      .addCase(loadWallPosts.rejected, (state) => {
        state.postsLoading = false;
      })

      // Create post
      .addCase(createPost.fulfilled, (state, action) => {
        state.posts.unshift(action.payload);
        if (state.profile) {
          state.profile.post_stats.total_posts += 1;
          state.profile.post_stats.last_post_date = action.payload.created_at;
        }
      })

      // Edit post
      .addCase(editPost.fulfilled, (state, action) => {
        const idx = state.posts.findIndex((p) => p.id === action.payload.id);
        if (idx !== -1) {
          state.posts[idx] = action.payload;
        }
      })

      // Delete post
      .addCase(deletePost.fulfilled, (state, action) => {
        state.posts = state.posts.filter((p) => p.id !== action.payload);
        if (state.profile) {
          state.profile.post_stats.total_posts = Math.max(
            0,
            state.profile.post_stats.total_posts - 1,
          );
        }
      })

      // Friends
      .addCase(loadFriends.pending, (state) => {
        state.friendsLoading = true;
      })
      .addCase(loadFriends.fulfilled, (state, action) => {
        state.friendsLoading = false;
        state.friends = action.payload;
      })
      .addCase(loadFriends.rejected, (state) => {
        state.friendsLoading = false;
      })

      // Incoming requests
      .addCase(loadIncomingRequests.fulfilled, (state, action) => {
        state.incomingRequests = action.payload;
      })

      // Outgoing requests
      .addCase(loadOutgoingRequests.fulfilled, (state, action) => {
        state.outgoingRequests = action.payload;
      })

      // Send friend request
      .addCase(sendRequest.fulfilled, (state) => {
        if (state.profile) {
          state.profile.friendship_status = 'pending_sent';
        }
      })

      // Reject request
      .addCase(rejectRequest.fulfilled, (state, action) => {
        state.incomingRequests = state.incomingRequests.filter(
          (r) => r.id !== action.payload,
        );
        state.outgoingRequests = state.outgoingRequests.filter(
          (r) => r.id !== action.payload,
        );
        if (state.profile && state.profile.friendship_id === action.payload) {
          state.profile.friendship_status = 'none';
          state.profile.is_friend = false;
          state.profile.friendship_id = null;
        }
      })

      // Avatar upload
      .addCase(uploadAvatar.pending, (state) => {
        state.avatarUploading = true;
      })
      .addCase(uploadAvatar.fulfilled, (state, action) => {
        state.avatarUploading = false;
        if (state.profile) {
          state.profile.avatar = action.payload;
        }
      })
      .addCase(uploadAvatar.rejected, (state) => {
        state.avatarUploading = false;
      })

      // Profile settings
      .addCase(updateProfileSettings.pending, (state) => {
        state.settingsUpdating = true;
      })
      .addCase(updateProfileSettings.fulfilled, (state) => {
        state.settingsUpdating = false;
      })
      .addCase(updateProfileSettings.rejected, (state) => {
        state.settingsUpdating = false;
      })

      // Username change
      .addCase(updateUsername.pending, (state) => {
        state.settingsUpdating = true;
      })
      .addCase(updateUsername.fulfilled, (state) => {
        state.settingsUpdating = false;
      })
      .addCase(updateUsername.rejected, (state) => {
        state.settingsUpdating = false;
      })

      // User characters
      .addCase(loadUserCharacters.pending, (state) => {
        state.charactersLoading = true;
      })
      .addCase(loadUserCharacters.fulfilled, (state, action) => {
        state.charactersLoading = false;
        state.characters = action.payload;
      })
      .addCase(loadUserCharacters.rejected, (state) => {
        state.charactersLoading = false;
      })

      // Profile background upload
      .addCase(uploadProfileBackground.pending, (state) => {
        state.settingsUpdating = true;
      })
      .addCase(uploadProfileBackground.fulfilled, (state, action) => {
        state.settingsUpdating = false;
        if (state.profile) {
          state.profile.profile_bg_image = action.payload;
        }
      })
      .addCase(uploadProfileBackground.rejected, (state) => {
        state.settingsUpdating = false;
      })

      // Profile background delete
      .addCase(deleteProfileBackground.pending, (state) => {
        state.settingsUpdating = true;
      })
      .addCase(deleteProfileBackground.fulfilled, (state) => {
        state.settingsUpdating = false;
        if (state.profile) {
          state.profile.profile_bg_image = null;
        }
      })
      .addCase(deleteProfileBackground.rejected, (state) => {
        state.settingsUpdating = false;
      });
  },
});

export const { resetUserProfile } = userProfileSlice.actions;
export default userProfileSlice.reducer;

// ── Selectors ──

export const selectUserProfile = (state: RootState) => state.userProfile.profile;
export const selectWallPosts = (state: RootState) => state.userProfile.posts;
export const selectPostsLoading = (state: RootState) => state.userProfile.postsLoading;
export const selectHasMorePosts = (state: RootState) => state.userProfile.hasMorePosts;
export const selectPostsPage = (state: RootState) => state.userProfile.postsPage;
export const selectFriends = (state: RootState) => state.userProfile.friends;
export const selectIncomingRequests = (state: RootState) => state.userProfile.incomingRequests;
export const selectOutgoingRequests = (state: RootState) => state.userProfile.outgoingRequests;
export const selectProfileLoading = (state: RootState) => state.userProfile.loading;
export const selectFriendsLoading = (state: RootState) => state.userProfile.friendsLoading;
export const selectAvatarUploading = (state: RootState) => state.userProfile.avatarUploading;
export const selectProfileError = (state: RootState) => state.userProfile.error;
export const selectUserCharacters = (state: RootState) => state.userProfile.characters;
export const selectCharactersLoading = (state: RootState) => state.userProfile.charactersLoading;
export const selectSettingsUpdating = (state: RootState) => state.userProfile.settingsUpdating;
